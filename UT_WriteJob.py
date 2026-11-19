import os
import tempfile
import unittest

# Module imports
from backend.Command import Command
from backend.Encryption import E_Mode
from backend.File import FileState
from backend.Job import Job
from backend.Tape import Tape
from backend.TableOfContent import TableOfContent
from backend.TapeDrive import TapeDrive
from backend.WriteJob import WriteJob


class UT_WriteJob(unittest.TestCase):

    """_summary_
    The whole run list on a fake drive (a regular file, rewind and eject are shell commands that leave a trace).
    Tests A:
        - A: rewind, TOC, files, TOC, rewind in this order; the last TOC is COMPLETE and holds the results
        - B: eject only on request
        - C: a file fails after the first TOC: no further file, the last TOC says FAILED, rewind still runs, no eject
        - D: requests that are refused up front
        - E: the drive idles until every checksum is known; both TOCs are equivalent (checksums included)
        - F: a file that cannot be read: the tape is not touched at all, no TOC is written
        - G: no passphrase needs unencrypted=True, and unencrypted excludes a passphrase
        - H: unencrypted: plain files on the tape, plain TOC without keys, no spool
    The fake tape is truncated by every write, so only the last tape file (the last TOC) is left on it.
    Depdencies:
    - openssl, /mnt/daten as a mount point (spool)
    """

    MOUNT: str = "/mnt/daten"
    PASSPHRASE: str = "passphrase"

    def setUp(self) -> None:
        if not os.path.ismount(self.MOUNT):
            self.skipTest(self.MOUNT + " is not a mount")
        Job.Stop()
        Job.Flush()
        Job.limit = 2

    def tearDown(self) -> None:
        Job.Flush()
        Job.limit = Job.DEFAULT_THREADLIMIT

    def _drive(self, tmp: str, tape: str = "8800") -> TapeDrive:
        td: TapeDrive = TapeDrive(os.path.join(tmp, "fake.bin"), "", drive_override=True)
        open(td.path, "wb").close()
        td.tapeOverride(Tape(tape, td.generic_path))
        log: str = os.path.join(tmp, "log")
        td.rewindCommand = Command("sh -c 'echo rewind >> " + log + "'")
        td.ejectCommand = Command("sh -c 'echo eject >> " + log + "'")
        return td

    def _input(self, tmp: str) -> str:
        src: str = os.path.join(tmp, "in")
        os.makedirs(os.path.join(src, "sub"))
        for rel in ["a.bin", "b b.bin", "sub/c.bin"]:
            with open(os.path.join(src, rel), "wb") as f:
                f.write(os.urandom(5000))
        return src

    def _log(self, tmp: str) -> list:
        try:
            with open(os.path.join(tmp, "log")) as f:
                return f.read().split()
        except FileNotFoundError:
            return []

    def _tapeCommands(self, job: WriteJob) -> list:
        """What the drive was told to do, in the order of the queue."""
        out: list = []
        for e in job.entries:
            entry = Job.Get(e)
            if entry.tape:
                out.append(entry.command.cmd)
        return out

    def test_A_wholeRunList(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            tocDir: str = os.path.join(tmp, "tocs"); os.makedirs(tocDir)
            job: WriteJob = WriteJob(self._input(tmp), td, self.PASSPHRASE, self.MOUNT, tocDir=tocDir)

            self.assertEqual(job.state, "NEW")
            job.queue()
            self.assertTrue(all(Job.Get(i).drive == td.id for i in job.entries))     # also checksum, encryption, closing steps
            self.assertEqual(set(Job.Registry(td.id)), set(job.entries))
            self.assertTrue(job.wait(60))

            self.assertEqual(job.state, "COMPLETED", str(job))
            self.assertEqual(self._log(tmp), ["rewind", "rewind"])      # before the first TOC and after the last one

            # order on the tape: rewind, TOC, 3 files in tape order, TOC, rewind
            commands: list = self._tapeCommands(job)
            self.assertEqual(len(commands), 7)
            self.assertIn("echo rewind", commands[0])
            self.assertIn("toc_start.json", commands[1])
            self.assertEqual([("0001.crypt" in c, "0002.crypt" in c, "0003.crypt" in c) for c in commands[2:5]],
                             [(True, False, False), (False, True, False), (False, False, True)])
            self.assertIn("toc_end.json", commands[5])
            self.assertIn("echo rewind", commands[6])

            # the last TOC is what is left on the fake tape: complete, same tape as the first one, results inside
            with open(td.path) as f:
                last: dict = TableOfContent.open(f.read(), self.PASSPHRASE)
            self.assertEqual(last["header"]["state"], "COMPLETE")
            self.assertEqual(last["header"]["fingerprint"], job.toc.header.fingerprint)
            files: list = last["body"]["folder"]["files"]
            self.assertEqual([f["id"] for f in files], [1, 2, 3])
            self.assertTrue(all(len(f["cksum"]["value"]) == 64 for f in files))        # SHA256 of every file
            self.assertTrue(all(f["state"] == "IDLE" for f in files))

            self.assertEqual(len(os.listdir(tocDir)), 1)                                # the copy of the last TOC
            self.assertFalse(os.path.exists(job.spool.path))                            # cleaned up
        print(".A_WHOLE_RUN_LIST")

    def test_B_ejectOnlyOnRequest(self) -> None:
        for eject in [False, True]:
            with tempfile.TemporaryDirectory() as tmp:
                td: TapeDrive = self._drive(tmp)
                job: WriteJob = WriteJob(self._input(tmp), td, self.PASSPHRASE, self.MOUNT, eject=eject)
                job.queue()
                self.assertTrue(job.wait(60))
                self.assertEqual(job.state, "COMPLETED")
                self.assertEqual(self._log(tmp), ["rewind", "rewind", "eject"] if eject else ["rewind", "rewind"])
            Job.Flush()
        print("B_EJECT_ON_REQUEST")

    def test_C_failedFileAbortsButClosesTheTape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            Job.limit = 1
            job: WriteJob = WriteJob(self._input(tmp), td, self.PASSPHRASE, self.MOUNT, eject=True)
            job.queue()
            write2: str = [e for phase, e in job.folder.files[1].entries if phase is FileState.WRITE][0]
            Job.Get(write2).prepare = lambda: os.remove(job.spool.file(2))     # the encrypted copy vanishes before the drive takes it
            self.assertTrue(job.wait(60))

            self.assertEqual(job.state, "FAILED")
            self.assertEqual([f.state for f in job.folder.files], [FileState.IDLE, FileState.ERROR, FileState.ERROR])
            self.assertEqual(self._log(tmp), ["rewind", "rewind"])      # closed anyway, and NOT ejected

            with open(td.path) as f:                                    # the last TOC was still written
                self.assertEqual(TableOfContent.open(f.read(), self.PASSPHRASE)["header"]["state"], "FAILED")
            self.assertFalse(os.path.exists(job.spool.path))
        print("C_FAILED_CLOSES_THE_TAPE")

    def test_D_refusedUpFront(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src: str = self._input(tmp)

            empty: str = os.path.join(tmp, "empty"); os.makedirs(empty)
            with self.assertRaises(ValueError):
                WriteJob(empty, self._drive(tmp), self.PASSPHRASE, self.MOUNT).queue()

            with self.assertRaises(ValueError):                         # write protected
                WriteJob(src, self._drive(tmp, "8890"), self.PASSPHRASE, self.MOUNT).queue()

            with self.assertRaises(ValueError):                         # no tape
                WriteJob(src, self._drive(tmp, "0000"), self.PASSPHRASE, self.MOUNT).queue()

            big: str = os.path.join(tmp, "big"); os.makedirs(big)
            with open(os.path.join(big, "huge.bin"), "wb") as f:
                f.truncate(200 * 10**9)                                 # sparse, LTO-1 holds 100 GB
            with self.assertRaises(ValueError):
                WriteJob(big, self._drive(tmp, "1800"), self.PASSPHRASE, self.MOUNT).queue()

            job: WriteJob = WriteJob(src, self._drive(tmp), self.PASSPHRASE, self.MOUNT)
            job.queue()
            with self.assertRaises(RuntimeError):                       # only once
                job.queue()
            job.wait(60)
            self.assertEqual(self._log(tmp), ["rewind", "rewind"])      # the refused ones did nothing to the tape
        print("D_REFUSED_UP_FRONT")

    def test_E_idleUntilBothTocsCouldBeWritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            job: WriteJob = WriteJob(self._input(tmp), td, self.PASSPHRASE, self.MOUNT)
            first: list = []
            original = job._firstToc
            job._firstToc = lambda: (original(), first.append(job.toc.sealed))      # what goes on the tape first
            job.queue()

            tape: list = [Job.Get(e) for e in job.entries if Job.Get(e).tape]
            checksums: list = [e for f in job.folder.files for phase, e in f.entries if phase is FileState.CKSUM_CALC]
            self.assertEqual(len(checksums), 3)
            rewind = tape[0]
            self.assertEqual(rewind.state.name, "WAITING_FOR_PARENT")               # the drive does not start yet
            self.assertEqual(self._log(tmp), [])

            self.assertTrue(job.wait(60))
            self.assertEqual(job.state, "COMPLETED", str(job))

            a: dict = TableOfContent.open(first[0], self.PASSPHRASE)
            b: dict = TableOfContent.open(job.toc.sealed, self.PASSPHRASE)
            self.assertEqual(a["header"]["state"], "IDLE")
            self.assertEqual(b["header"]["state"], "COMPLETE")
            self.assertEqual(TableOfContent.differences(a, b), [])                  # equivalent, checksums included
            self.assertTrue(all(len(f["cksum"]["value"]) == 64 for f in a["body"]["folder"]["files"]))
        print("E_EQUIVALENT_TOCS")

    def test_F_unreadableFileLeavesTheTapeAlone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            tocDir: str = os.path.join(tmp, "tocs"); os.makedirs(tocDir)
            with open(td.path, "w") as f:
                f.write("what was on the tape")
            job: WriteJob = WriteJob(self._input(tmp), td, self.PASSPHRASE, self.MOUNT, tocDir=tocDir, eject=True)
            os.remove(job.folder.files[1].path.path)        # the second file vanishes before its checksum
            job.queue()
            self.assertTrue(job.wait(60))

            self.assertEqual(job.state, "FAILED")
            with open(td.path) as f:
                self.assertEqual(f.read(), "what was on the tape")      # no TOC, no file
            self.assertEqual(self._log(tmp), ["rewind"])                # only the closing rewind, no eject
            self.assertEqual(os.listdir(tocDir), [])
            self.assertFalse(os.path.exists(job.spool.path))
        print("F_TAPE_UNTOUCHED")

    def test_G_passphraseRules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src: str = self._input(tmp)
            td: TapeDrive = self._drive(tmp)

            with self.assertRaisesRegex(ValueError, "Passphrase for encryption required"):
                WriteJob(src, td, "", self.MOUNT)
            with self.assertRaises(ValueError):                                     # both at once
                WriteJob(src, td, self.PASSPHRASE, self.MOUNT, unencrypted=True)
            with self.assertRaises(ValueError):                                     # NONE is what unencrypted is for
                WriteJob(src, td, self.PASSPHRASE, self.MOUNT, encryption=E_Mode.NONE)
            WriteJob(src, td, "", self.MOUNT, unencrypted=True)                     # fine
        print("G_PASSPHRASE_RULES")

    def test_H_unencrypted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            src: str = self._input(tmp)
            job: WriteJob = WriteJob(src, td, "", self.MOUNT, unencrypted=True)
            job.queue()
            self.assertTrue(job.wait(60))
            self.assertEqual(job.state, "COMPLETED", str(job))

            commands: list = self._tapeCommands(job)
            self.assertEqual(len(commands), 7)
            self.assertTrue(all(".crypt" not in c for c in commands))               # the originals go to the tape
            self.assertIn(os.path.join(src, "a.bin"), commands[2])

            with open(td.path) as f:
                text: str = f.read()
            last: dict = TableOfContent.open(text)                                  # no passphrase
            self.assertEqual(last["header"]["body_cipher"], "NONE")
            self.assertEqual(last["header"]["state"], "COMPLETE")
            files: list = last["body"]["folder"]["files"]
            self.assertEqual([f["encryption"]["mode"] for f in files], ["NONE"] * 3)
            self.assertTrue(all(f["encryption"]["key"]["value"] == "" for f in files))
            self.assertEqual(os.listdir(src).count("a.bin"), 1)                     # nothing was added next to the originals
            self.assertFalse(any(n.endswith(".crypt") for n in os.listdir(src)))
        print("H_UNENCRYPTED")


if __name__ == "__main__":
    unittest.main()

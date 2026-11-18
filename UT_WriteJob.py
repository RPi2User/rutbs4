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
        - C: a failing file: no further file, the last TOC says FAILED, rewind still runs, no eject
        - D: requests that are refused up front
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
        td.tapeOverride(Tape(tape))
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
            os.remove(job.folder.files[1].path.path)        # the second file vanishes before it is processed
            job.queue()
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


if __name__ == "__main__":
    unittest.main()

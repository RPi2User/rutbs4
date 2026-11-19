import copy
import os
import tempfile
import unittest

# Module imports
from backend.Checksum import ChecksumType
from backend.Encryption import E_Mode, Key
from backend.File import File, FileState
from backend.Folder import Folder
from backend.Job import Job
from backend.ReadJob import ReadJob
from backend.TD_Pool import TD_Pool
from backend.TableOfContent import TableOfContent, TOC_Header, TOC_WrongPassphrase
from backend.TapeDrive import TD_State
from backend.WriteJob import WriteJob


class UT_ReadJob(unittest.TestCase):

    """_summary_
    The reading side: restoring a File from its TOC entry, the comparison of the two TOCs and, on the real
    drive, the whole way tape -> files.
    Tests A:
        - A: a Key read back from a TOC is the same key
        - B: a File restored from its TOC entry decrypts and validates; a wrong checksum is a MISMATCH
        - C: the comparison of the first and the last TOC
        - D: a TOC cannot make a file leave the target directory
        - E: (real drive) write a folder, read it back: files identical, TOCs compared, tape rewound, NOT ejected
        - F: (real drive) a wrong passphrase queues nothing
    Depdencies:
    - openssl, /mnt/daten as a mount point (spool)
    - E and F write to the FIRST tape drive from its begin: only with RUTBS_TEST_TAPE=1 (RUTBS_TEST_MOUNT=<mount point>)
    """

    MOUNT: str = os.environ.get("RUTBS_TEST_MOUNT", "/mnt/daten")      # a mount point for the spool and the files
    PASSPHRASE: str = "passphrase"

    def setUp(self) -> None:
        Job.Stop()
        Job.Flush()
        Job.limit = 2

    def tearDown(self) -> None:
        Job.Flush()
        Job.limit = Job.DEFAULT_THREADLIMIT

    def _input(self, tmp: str) -> str:
        src: str = os.path.join(tmp, "in")
        os.makedirs(os.path.join(src, "sub"))
        for rel, size in [("a.bin", 5000), ("b b.bin", 300000), ("sub/c.bin", 0), ("sub/d.bin", 70000)]:
            with open(os.path.join(src, rel), "wb") as f:
                f.write(os.urandom(size))
        return src

    def _tocs(self, tmp: str) -> tuple:
        """First and last TOC as TableOfContent.open() returns them, and the folder."""
        folder: Folder = Folder(self._input(tmp), ChecksumType.SHA256, E_Mode.AES256CBC)
        toc: TableOfContent = TableOfContent(folder, TOC_Header(self._fakeDrive(), 2))
        for f in folder.files:                      # the write job knows every checksum before the first TOC
            f.cksum.create()
            Job.Run(f.cksum.cmd, 60000)
            f.cksum._status()
        first: dict = {"header": toc.header._asdict(), "body": {"folder": folder._asdict()}}
        last: dict = {"header": copy.deepcopy(first["header"]), "body": {"folder": folder._asdict()}}
        last["header"]["state"] = "COMPLETE"
        return first, last, folder

    def _fakeDrive(self):
        from backend.Tape import Tape
        from backend.TapeDrive import TapeDrive
        td: TapeDrive = TapeDrive("/dev/null", "", drive_override=True)
        td.tapeOverride(Tape("8800", td.generic_path))
        return td

    def test_A_keyFromTheToc(self) -> None:
        key: Key = Key()
        again: Key = Key(key.length, key.value, key.iv)
        self.assertEqual((again.value, again.iv, again.length), (key.value, key.iv, key.length))
        with self.assertRaises(ValueError):
            Key(key.length, key.value[:-2], key.iv)
        print(".A_KEY_FROM_TOC")

    def test_B_restoreFromEntry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, last, folder = self._tocs(tmp)
            target: str = os.path.join(tmp, "out")

            for f in folder.files:                                              # encrypt as the write job does
                self.assertTrue(Job.Wait([f.Encrypt(os.path.join(tmp, "%04d.crypt" % f.id))], 30))
            entries: list = last["body"]["folder"]["files"]

            restored: list = [File.Restore(e, target) for e in entries]
            ids: list = []
            for f, original in zip(restored, folder.files):
                self.assertEqual(f.size, original.size)
                f.cryptPath = original.cryptPath                                # the ciphertext "came from the tape"
                ids.append(f.Validate(dependsOn=f.Decrypt(f.path.path)))
            self.assertTrue(Job.Wait(ids, 60))

            for f, original in zip(restored, folder.files):
                self.assertEqual(f.state, FileState.IDLE, str(f))
                with open(f.path.path, "rb") as a, open(original.path.path, "rb") as b:
                    self.assertEqual(a.read(), b.read())
            self.assertTrue(os.path.isdir(os.path.join(target, "sub")))

            # one wrong checksum in the TOC
            entry: dict = copy.deepcopy(entries[0])
            entry["cksum"]["value"] = "0" * 64
            bad: File = File.Restore(entry, os.path.join(tmp, "out2"))
            bad.cryptPath = folder.files[0].cryptPath
            self.assertTrue(Job.Wait([bad.Validate(dependsOn=bad.Decrypt(bad.path.path))], 60))
            self.assertEqual(bad.state, FileState.MISMATCH)
        print("B_RESTORE_FROM_ENTRY")

    def test_BB_restorePlainEntry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, last, folder = self._tocs(tmp)
            entry: dict = copy.deepcopy(last["body"]["folder"]["files"][0])
            entry["encryption"] = {"mode": "NONE", "key": {"length": "medium", "value": "", "iv": ""}}

            f: File = File.Restore(entry, os.path.join(tmp, "out"))      # an empty value must not become a random key
            self.assertEqual((f.encryption_scheme.mode, f.encryption_scheme.key.value, f.encryption_scheme.key.iv), (E_Mode.NONE, "", ""))
            self.assertEqual(f.Decrypt(f.path.path, dependsOn="x"), "x")     # nothing to do
        print("BB_RESTORE_PLAIN_ENTRY")

    def test_C_differences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, last, _ = self._tocs(tmp)
            self.assertEqual(TableOfContent.differences(first, last), [])       # only the state is a result

            other: dict = copy.deepcopy(last)
            other["header"]["fingerprint"] = "another"
            other["body"]["folder"]["files"][1]["encryption"]["key"]["iv"] = "00"
            other["body"]["folder"]["files"][2]["size"] = 1
            other["body"]["folder"]["files"][3]["cksum"]["value"] = "ff"        # both TOCs hold the checksums
            found: str = " ".join(TableOfContent.differences(first, other))
            for expected in ["header.fingerprint", "file 2: iv", "file 3: size", "file 4: cksum.value"]:
                self.assertIn(expected, found)
            for f in last["body"]["folder"]["files"]:                           # no key material in the report
                self.assertNotIn(f["encryption"]["key"]["value"], found)
                self.assertNotIn(f["encryption"]["key"]["iv"], found)

            short: dict = copy.deepcopy(last)
            short["body"]["folder"]["files"].pop()
            self.assertIn("files", TableOfContent.differences(first, short)[0])
        print("C_DIFFERENCES")

    def test_D_staysInTheTarget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, last, _ = self._tocs(tmp)
            entry: dict = copy.deepcopy(last["body"]["folder"]["files"][0])
            entry["path"]["relPath"] = "../escaped.bin"
            with self.assertRaises(ValueError):
                File.Restore(entry, os.path.join(tmp, "out"))
            self.assertFalse(os.path.exists(os.path.join(tmp, "escaped.bin")))
        print("D_STAYS_IN_TARGET")

    # === REAL DRIVE ==========================================================

    def _realDrive(self):
        if os.environ.get("RUTBS_TEST_TAPE") != "1":
            self.skipTest("RUTBS_TEST_TAPE=1 is not set: this test overwrites the tape in the drive")
        drives: list = TD_Pool().gatherDrives()
        if not drives:
            self.skipTest("no tape drive")
        return drives[0]

    def test_E_realDriveRoundTrip(self) -> None:
        td = self._realDrive()
        Job.limit = 4
        with tempfile.TemporaryDirectory(dir=self.MOUNT) as tmp:
            src: str = self._input(tmp)
            tocs: str = os.path.join(tmp, "tocs"); os.makedirs(tocs)
            target: str = os.path.join(tmp, "restored")

            write: WriteJob = WriteJob(src, td, self.PASSPHRASE, self.MOUNT, tocDir=tocs)    # never ejects
            write.queue()
            self.assertTrue(write.wait(600))
            self.assertEqual(write.state, "COMPLETED", str(write))

            job: ReadJob = ReadJob(td, target, self.MOUNT, tocDir=tocs)
            header: dict = job.open()
            self.assertEqual(header["first"]["state"], "IDLE")
            self.assertEqual(header["last"]["state"], "COMPLETE")
            self.assertEqual(header["first"]["fingerprint"], write.toc.header.fingerprint)

            job.queue(self.PASSPHRASE)
            self.assertTrue(all(Job.Get(i).drive == td.id for i in job.entries))     # decrypt, checksum, closing step too
            self.assertTrue(job.wait(600))
            self.assertEqual(job.state, "COMPLETED", str(job))
            self.assertEqual(job.messages, [])

            for f in write.folder.files:
                with open(f.path.path, "rb") as a, open(os.path.join(target, f.path.relPath), "rb") as b:
                    self.assertEqual(a.read(), b.read(), f.path.relPath)
            self.assertEqual(len([n for n in os.listdir(tocs) if n.endswith(".plain.json")]), 2)
            self.assertFalse(os.path.exists(job.spool.path))
            self.assertEqual(td.state, TD_State.IDLE)                        # (reading the state derives the position)
            self.assertTrue(td.tape.begin_of_tape)                           # rewound, and still in the drive
        print("E_REAL_ROUND_TRIP")

    def test_F_wrongPassphraseQueuesNothing(self) -> None:
        td = self._realDrive()
        with tempfile.TemporaryDirectory(dir=self.MOUNT) as tmp:
            job: ReadJob = ReadJob(td, os.path.join(tmp, "restored"), self.MOUNT)
            job.open()
            with self.assertRaises(TOC_WrongPassphrase):
                job.queue("not the passphrase")
            self.assertEqual(job.state, "OPEN")
            self.assertFalse(os.path.exists(os.path.join(tmp, "restored")))
        print("F_WRONG_PASSPHRASE")


if __name__ == "__main__":
    unittest.main()

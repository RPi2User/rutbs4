import hashlib
import os
import subprocess
import tempfile
import time
import unittest

# Module imports
from backend.Checksum import ChecksumType
from backend.Encryption import E_Mode
from backend.File import FileState
from backend.Folder import Folder
from backend.Job import Job, EntryState
from backend.Spool import Spool
from backend.Tape import Tape
from backend.TapeDrive import TapeDrive


class UT_Folder(unittest.TestCase):

    """_summary_
    Tests A:
        - AA-AC: File collection, own Key/IV and Command per File, odd file names
        - AD:    Sub directories are scanned, tape order = sorted relative paths, ids start at 1
        - AE:    Encrypted Files go to the spool, named after the tape file number
        - B:     Single File end-to-end via Job against a drive_override TapeDrive
        - C:     Job-chain structure for checksum -> encrypt -> write, and NONE/NONE
        - D:     A failing File aborts the rest of the write
    Depdencies:
    - openssl (to build the expected ciphertext for the roundtrip check)
    """

    def setUp(self) -> None:
        Job.Stop()
        Job.Flush()

    def tearDown(self) -> None:
        Job.Stop()
        Job.Flush()

    def _fakeTape(self, tmp: str) -> TapeDrive:
        tape_path: str = os.path.join(tmp, "faketape.bin")
        open(tape_path, "wb").close()
        td: TapeDrive = TapeDrive(path=tape_path, generic_path="", drive_override=True)
        td.tapeOverride(Tape("3800", td.generic_path))  # LTO-3, no write protect
        return td

    def _waitAll(self, entries, timeoutSec: float = 10) -> None:
        end: float = time.time() + timeoutSec
        while any(Job.Get(e).state not in Job.FINISHED for e in entries):
            if time.time() > end:
                self.fail("[FAIL] Timeout: " + str(Job.Registry()))
            Job.Refresh()
            time.sleep(.01)

    def test_AA_collectsFiles(self) -> None:
        with tempfile.TemporaryDirectory() as src:
            for n in range(3):
                with open(os.path.join(src, f"f{n}.txt"), "w") as f:
                    f.write("data" + str(n))
            os.makedirs(os.path.join(src, "subdir"))  # an empty directory is not a file

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.NONE)

            self.assertEqual(len(folder.files), 3)
            self.assertEqual({f.path.name for f in folder.files}, {"f0.txt", "f1.txt", "f2.txt"})
        print(".AA_COLLECTS_FILES")

    def test_AB_ownKeyPerFile(self) -> None:
        with tempfile.TemporaryDirectory() as src:
            for n in range(2):
                with open(os.path.join(src, f"f{n}.txt"), "w") as f:
                    f.write("data" + str(n))

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.AES256CBC)

            self.assertEqual(len(folder.files), 2)
            a, b = (f.encryption_scheme for f in folder.files)
            self.assertNotEqual(a.key.value, b.key.value)       # every File has its own Key ...
            self.assertNotEqual(a.key.iv, b.key.iv)             # ... and its own IV
            self.assertEqual(a.mode, E_Mode.AES256CBC)          # the mode comes from the Folder
            self.assertEqual(b.mode, E_Mode.AES256CBC)
            self.assertIsNot(a.cmd, b.cmd)                      # independent Commands for Job
        print("AB_OWN_KEY")

    def test_AC_oddFileNames(self) -> None:
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            names = {"with space.txt", "it's.txt"}
            for name in names:
                with open(os.path.join(src, name), "w") as f:
                    f.write(name)

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.AES256CBC)
            self.assertEqual({f.path.name for f in folder.files}, names)

            entries = folder.queueWrite(self._fakeTape(dst))
            self._waitAll(entries)

            for entry, file in zip(entries, folder.files):
                self.assertEqual(Job.Get(entry).state, EntryState.COMPLETED)
                self.assertEqual(file.cksum.value, hashlib.sha256(file.path.name.encode()).hexdigest())
                key: str = file.encryption_scheme.key.value
                self.assertNotIn(key, str(Job.Get(entry)))  # the key is not part of any command
                self.assertNotIn(key, str(Job.Get(Job.Get(entry).dependsOn)))
        print("AC_ODD_FILE_NAMES")

    def test_AD_recursiveAndOrdered(self) -> None:
        with tempfile.TemporaryDirectory() as src:
            for rel in ["z.txt", "m.txt", "a/b.txt", "a/a.txt", "a/deep/x.txt"]:
                os.makedirs(os.path.dirname(os.path.join(src, rel)), exist_ok=True)
                with open(os.path.join(src, rel), "w") as f:
                    f.write(rel)

            folder: Folder = Folder(src, ChecksumType.NONE, E_Mode.NONE)

            self.assertEqual([f.path.relPath for f in folder.files],
                             ["a/a.txt", "a/b.txt", "a/deep/x.txt", "m.txt", "z.txt"])
            self.assertEqual([f.id for f in folder.files], [1, 2, 3, 4, 5])     # tape file 0 is the TOC
            self.assertEqual(folder.files[0].path.parent, os.path.join(src, "a"))
            self.assertEqual(folder.files[0].path.context, src)
        print("AD_RECURSIVE_ORDERED")

    @unittest.skipUnless(os.path.ismount("/mnt/daten"), "needs /mnt/daten as a mount")
    def test_AE_spool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src: str = os.path.join(tmp, "src")
            os.makedirs(src)
            with open(os.path.join(src, "f.txt"), "w") as f:
                f.write("data")

            spool: Spool = Spool("/mnt/daten", "ut-folder")
            spool.create()
            try:
                folder: Folder = Folder(src, ChecksumType.NONE, E_Mode.AES256CBC)
                entries = folder.queueWrite(self._fakeTape(tmp), spool=spool)
                self._waitAll(entries)

                self.assertEqual(Job.Get(entries[0]).state, EntryState.COMPLETED)
                self.assertTrue(os.path.exists(os.path.join(spool.path, "0001.crypt")))
                self.assertFalse(os.path.exists(os.path.join(src, "f.txt.crypt")))   # nothing next to the original
            finally:
                spool.remove()
        print("AE_SPOOL")

    def test_BA_singleFileRoundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            content: bytes = os.urandom(2048)
            src_path: str = os.path.join(src, "payload.bin")
            with open(src_path, "wb") as f:
                f.write(content)

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.AES256CBC)
            key = folder.files[0].encryption_scheme.key
            td: TapeDrive = self._fakeTape(dst)

            entries = folder.queueWrite(td)
            Job.Work(20)
            self._waitAll(entries)
            Job.Stop()

            self.assertEqual(Job.Get(entries[0]).state, EntryState.COMPLETED)
            self.assertEqual(folder.files[0].state, FileState.IDLE)     # derived from the Job entries, no finalize step
            self.assertEqual(folder.files[0].cksum.value, hashlib.sha256(content).hexdigest())

            with open(td.path, "rb") as f:
                on_tape: bytes = f.read()
            self.assertNotEqual(on_tape, content)  # sanity: it really is encrypted, not plaintext

            # Decrypt what actually ended up "on tape" with the Key/IV of the File and compare to the original.
            # (openssl -pbkdf2 salts every encryption run, so two independent encrypt runs never produce
            # byte-identical ciphertext even with the same key/iv - only the roundtrip is deterministic.)
            decrypted: str = os.path.join(dst, "roundtrip.plain")
            subprocess.run(
                f"openssl aes-256-cbc -pbkdf2 -d -iv {key.iv} -k {key.value} "
                f"-in '{td.path}' -out '{decrypted}'",
                shell=True, check=True)

            with open(decrypted, "rb") as f:
                self.assertEqual(f.read(), content)
        print("BA_SINGLE_FILE_ROUNDTRIP")

    def test_CA_chainStructure(self) -> None:
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            for n in range(2):
                with open(os.path.join(src, f"f{n}.txt"), "w") as f:
                    f.write("x" * 100)

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.AES256CBC)
            td: TapeDrive = self._fakeTape(dst)

            entries = folder.queueWrite(td)
            self.assertEqual(len(entries), 2)

            for write_id in entries:
                write_entry = Job.Get(write_id)
                self.assertEqual(write_entry.tape, td.path)
                encrypt_entry = Job.Get(write_entry.dependsOn)
                self.assertIn("openssl", encrypt_entry.command.cmd)
                checksum_entry = Job.Get(encrypt_entry.dependsOn)
                self.assertIn("openssl sha256", checksum_entry.command.cmd)
                self.assertEqual(checksum_entry.dependsOn, "")

            self._waitAll(entries)
            Job.Stop()
        print("CA_CHAIN_STRUCTURE")

    def test_CB_noChecksumNoEncryption(self) -> None:
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            src_path: str = os.path.join(src, "plain.txt")
            with open(src_path, "w") as f:
                f.write("plaintext, no checksum, no encryption")

            folder: Folder = Folder(src, ChecksumType.NONE, E_Mode.NONE)
            td: TapeDrive = self._fakeTape(dst)

            entries = folder.queueWrite(td)
            write_entry = Job.Get(entries[0])
            self.assertEqual(write_entry.dependsOn, "")  # nothing to depend on
            self.assertIn("if='" + src_path + "'", write_entry.command.cmd)  # reads the plain file directly

            self._waitAll(entries)
            Job.Stop()

            with open(src_path, "rb") as f:
                expected = f.read()
            with open(td.path, "rb") as f:
                on_tape = f.read()
            self.assertEqual(on_tape, expected)
        print("CB_NO_CKSUM_NO_ENC")

    def test_DA_failedFileAbortsWrite(self) -> None:
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            for n in range(3):
                with open(os.path.join(src, f"f{n}.txt"), "w") as f:
                    f.write("data" + str(n))

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.AES256CBC)
            os.remove(folder.files[1].path.path)    # the second File vanishes before it is processed

            Job.limit = 1                           # one after the other, so the outcome is fixed
            entries = folder.queueWrite(self._fakeTape(dst), runlist="write-1")
            self._waitAll(entries)
            Job.limit = Job.DEFAULT_THREADLIMIT

            self.assertEqual(Job.Get(entries[0]).state, EntryState.COMPLETED)   # was on its way already
            self.assertEqual(Job.Get(entries[1]).state, EntryState.FAILED)
            self.assertEqual(Job.Get(entries[2]).state, EntryState.FAILED)      # aborted ...
            self.assertFalse(folder.files[2].cksum.cmd.didRun)                  # ... before anything ran
            self.assertEqual([f.state for f in folder.files], [FileState.IDLE, FileState.ERROR, FileState.ERROR])
        print("DA_FAILED_FILE_ABORTS")


if __name__ == '__main__':
    print("UT_Folder:")
    unittest.main()

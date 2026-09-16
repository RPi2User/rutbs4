import hashlib
import os
import subprocess
import tempfile
import time
import unittest

# Module imports
from backend.Checksum import ChecksumType
from backend.Encryption import E_Mode
from backend.Folder import Folder
from backend.Job import Job, EntryState
from backend.Tape import Tape
from backend.TapeDrive import TapeDrive


class UT_Folder(unittest.TestCase):

    """_summary_
    Tests A:
        - AA-AB: File collection, shared Key/independent Command per File
        - B:     Single File end-to-end via Job against a drive_override TapeDrive
        - C:     Job-chain structure for checksum -> encrypt -> write, and NONE/NONE
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
        td.tapeOverride(Tape("3800"))  # LTO-3, no write protect
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
            os.makedirs(os.path.join(src, "subdir"))  # must be ignored, -maxdepth 1 -type f

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.NONE)

            self.assertEqual(len(folder.files), 3)
            self.assertEqual({f.path.name for f in folder.files}, {"f0.txt", "f1.txt", "f2.txt"})
        print(".AA_COLLECTS_FILES")

    def test_AB_sharedKeyIndependentCommand(self) -> None:
        with tempfile.TemporaryDirectory() as src:
            for n in range(2):
                with open(os.path.join(src, f"f{n}.txt"), "w") as f:
                    f.write("data" + str(n))

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.AES256CBC)

            self.assertEqual(len(folder.files), 2)
            keys = {f.encryption_scheme.key for f in folder.files}
            self.assertEqual(len(keys), 1)                      # same Key object shared
            self.assertIs(folder.files[0].encryption_scheme.key, folder.key)

            schemes = {id(f.encryption_scheme) for f in folder.files}
            self.assertEqual(len(schemes), 2)                   # but independent Encryption/Command
            self.assertIsNot(folder.files[0].encryption_scheme.cmd, folder.files[1].encryption_scheme.cmd)
        print("AB_SHARED_KEY")

    def test_BA_singleFileRoundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            content: bytes = os.urandom(2048)
            src_path: str = os.path.join(src, "payload.bin")
            with open(src_path, "wb") as f:
                f.write(content)

            folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.AES256CBC)
            key = folder.key
            td: TapeDrive = self._fakeTape(dst)

            entries = folder.queueWrite(td)
            Job.Work(20)
            self._waitAll(entries)
            Job.Stop()
            folder.finalizeChecksums()

            self.assertEqual(Job.Get(entries[0]).state, EntryState.COMPLETED)
            self.assertEqual(folder.files[0].cksum.value, hashlib.sha256(content).hexdigest())

            with open(td.path, "rb") as f:
                on_tape: bytes = f.read()
            self.assertNotEqual(on_tape, content)  # sanity: it really is encrypted, not plaintext

            # Decrypt what actually ended up "on tape" with the shared Key/IV and compare to the original.
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


if __name__ == '__main__':
    print("UT_Folder:")
    unittest.main()

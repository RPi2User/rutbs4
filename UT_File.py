import hashlib
import os
import tempfile
import unittest

# Module imports
from backend.Checksum import Checksum, ChecksumState, ChecksumType
from backend.Command import Command
from backend.Encryption import E_Mode
from backend.File import File, FileState, FilePath
from backend.Job import Job
from backend.Tape import Tape
from backend.TapeDrive import TapeDrive

class UT_File(unittest.TestCase):

    """_summary_
    Tests A: sanity, touch, remove, append (fixtures)
    Tests B: the phases (Validate, Encrypt, Write, Read, Decrypt) against a fake tape, no fixtures
        - BA: the state is derived from the Job entries
        - BB: phases with nothing to do pass the chain on
        - BC: a File goes onto the tape and comes back
        - BD: a damaged tape is noticed by the last Validate()
        - BE: refused phases
    """

    def setUp(self) -> None:
        Job.Stop()
        Job.Flush()

    def tearDown(self) -> None:
        Job.Flush()

    def _tape(self, tmp: str) -> TapeDrive:
        path: str = os.path.join(tmp, "faketape.bin")
        open(path, "wb").close()
        td: TapeDrive = TapeDrive(path=path, generic_path="", drive_override=True)
        td.tapeOverride(Tape("3800"))
        return td

    def _source(self, tmp: str, content: bytes, mode: E_Mode) -> File:
        path: str = os.path.join(tmp, "payload.bin")
        with open(path, "wb") as f:
            f.write(content)
        file: File = File(1, path, tmp)
        file.encryption_scheme.mode = mode
        return file

    CONTEXT: str = "/mnt/daten/testfiles/rutbs4"

    AA_PATH: str = "/mnt/daten/testfiles/rutbs4/file/2mib.file"
    AB_TOUCH: str = "/mnt/daten/testfiles/rutbs4/file/delete.me"

    AC_TOUCHFAIL: str = "/mnt/daten/testfiles/rutbs/invalid_dir/invalid_file_name.ee4097576b5b6fbace743b2532eda18b0fe08763ce3611c535534ac3a9208ddc"
    AD_DELETE: str = AB_TOUCH
    AE_APPEND: str = CONTEXT + "/file/append.txt"

    SHA256: str = "ee4097576b5b6fbace743b2532eda18b0fe08763ce3611c535534ac3a9208ddc"
    FOX: str = "The quick brown fox jumps over the lazy dog"

    def test_AA_sanity(self)-> None:
        f: File = File(1, self.AA_PATH, self.CONTEXT)

        try:
            self.assertEqual(f.id, 1)
            self.assertEqual(f.size, 2097152)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(len(f.state_msg), 0)
            self.assertEqual(f.path.path, "/mnt/daten/testfiles/rutbs4/file/2mib.file")
            self.assertEqual(f.path.name, "2mib.file")
            self.assertEqual(f.path.context, self.CONTEXT)
            self.assertEqual(f.path.parent, "/mnt/daten/testfiles/rutbs4/file")

            self.assertIsInstance(f.path, FilePath)
            self.assertIsInstance(f.cksum, Checksum)
            self.assertIsInstance(f.cmd, Command)

        except AssertionError:
            print(f)
            raise

        print(".A_SANITY")

    def test_AB_touch(self) -> None:
        f: File = File(1, self.AB_TOUCH, self.CONTEXT, True)
        try:
            self.assertEqual(f.size, 0)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(len(f.state_msg), 0)
        except AssertionError:
            print(f)
            raise

        print("B_TOUCH")

    def test_AC_touchFail(self) -> None:
        # Checks if constructor raises FileNotFoundError when createFile := False (default)
        # and file (indeed) not avaiable

        with self.assertRaises(FileNotFoundError):
            f: File = File(1, self.AC_TOUCHFAIL, self.CONTEXT)

        print("C_TOUCHFAIL")

    def test_AD_Delete(self) -> None:
        f: File = File(1, self.AD_DELETE, self.CONTEXT) # file currently avail @ f.path.path

        try:
            f.remove()
            #str(f)      # TODO Currently deletion is blocking so an external refresh was necessary

            self.assertEqual(f.size, -1)
            self.assertEqual(f.state, FileState.REMOVED)
        except AssertionError:
            print(f)
            raise

        print("D_DELETE")

    def test_AE_Append(self) -> None:
        """
        This tests File.append(str). During this test a append.txt will be created on FS.
        One Pangram (the quick brown fox...) and a "TESTSTRING".
        This tests validates 
        - file-size change after appending
        - no errors occur during append

        """
        f: File = File(1, self.AE_APPEND, self.CONTEXT, True)

        try:
            self.assertEqual(f.size, 0)
            f.append(self.FOX)

            self.assertEqual(f.size, len(self.FOX))
            self.assertEqual(f.state, FileState.IDLE)

            f.append("\nTESTSTRING")
            self.assertEqual(f.size, len(self.FOX) + 11)

            f.remove()
            str(f)

            self.assertEqual(f.size, -1)
            self.assertEqual(f.state, FileState.REMOVED)
            self.assertEqual(len(f.state_msg), 0)

        except AssertionError:
            print(f)
            raise
        print("E_APPEND")

    def test_BA_stateIsDerived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file: File = self._source(tmp, b"data", E_Mode.NONE)
            self.assertEqual(file.state, FileState.IDLE)

            entry: str = file.Validate()
            self.assertEqual(file.state, FileState.QUEUED)
            self.assertEqual(file.entries, [(FileState.CKSUM_CALC, entry)])

            self.assertTrue(Job.Wait([entry], 10))
            self.assertEqual(file.state, FileState.IDLE)
            self.assertEqual(file.cksum.value, hashlib.sha256(b"data").hexdigest())
        print("BA_STATE_DERIVED")

    def test_BB_nothingToDoPassesOn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file: File = self._source(tmp, b"data", E_Mode.NONE)
            file.cksum.setType(ChecksumType.NONE)

            self.assertEqual(file.Validate(dependsOn="parent"), "parent")
            self.assertEqual(file.Encrypt(dependsOn="parent"), "parent")
            self.assertEqual(file.Decrypt(tmp + "/x", dependsOn="parent"), "parent")
            self.assertEqual(file.entries, [])
        print("BB_PASS_ON")

    def _writeAndRestore(self, tmp: str, mode: E_Mode, damage: bool) -> File:
        content: bytes = os.urandom(4096)
        td: TapeDrive = self._tape(tmp)
        file: File = self._source(tmp, content, mode)

        # forward: checksum, encrypt, tape
        step: str = file.Validate(runlist="write")
        step = file.Encrypt(runlist="write", dependsOn=step)
        step = file.Write(td, runlist="write", dependsOn=step)
        self.assertTrue(Job.Wait([step], 30))
        self.assertEqual(file.state, FileState.IDLE)
        self.assertEqual(file.cksum.value, hashlib.sha256(content).hexdigest())

        if damage:
            with open(td.path, "r+b") as f:
                f.seek(100)
                f.write(b"\xff\xff\xff\xff")

        # back: tape, decrypt, compare with the stored checksum - queued in one go
        target: str = os.path.join(tmp, "restored.crypt" if mode is not E_Mode.NONE else "restored.bin")
        step = file.Read(td, target, runlist="read")
        step = file.Decrypt(os.path.join(tmp, "restored.bin"), runlist="read", dependsOn=step)
        step = file.Validate(runlist="read", dependsOn=step)
        self.assertTrue(Job.Wait([step], 30))

        if not damage:
            with open(os.path.join(tmp, "restored.bin"), "rb") as f:
                self.assertEqual(f.read(), content)
        return file

    def test_BC_tapeAndBack(self) -> None:
        for mode in [E_Mode.NONE, E_Mode.AES256CBC, E_Mode.AES128CTR]:
            with tempfile.TemporaryDirectory() as tmp:
                file: File = self._writeAndRestore(tmp, mode, damage=False)
                self.assertEqual(file.state, FileState.IDLE, mode.name)
                self.assertEqual(file.state_msg, [])
        print("BC_TAPE_AND_BACK")

    def test_BD_damagedTape(self) -> None:
        for mode in [E_Mode.NONE, E_Mode.AES128CTR]:      # CBC would already fail to decrypt, see UT_Encryption
            with tempfile.TemporaryDirectory() as tmp:
                file: File = self._writeAndRestore(tmp, mode, damage=True)
                self.assertEqual(file.state, FileState.MISMATCH, mode.name)
        print("BD_DAMAGED_TAPE")

    def test_BE_refusals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file: File = self._source(tmp, b"data", E_Mode.AES256CBC)
            td: TapeDrive = self._tape(tmp)

            with self.assertRaises(RuntimeError):
                file.Write(td)                  # Encrypt() first
            with self.assertRaises(RuntimeError):
                file.Decrypt(tmp + "/x")        # nothing to decrypt yet

            file.Validate()
            with self.assertRaises(RuntimeError):
                file.Validate()                 # the first checksum has not run yet

            Job.Flush()
            fresh: File = self._source(tmp, b"data", E_Mode.NONE)
            fresh.state = FileState.ERROR       # final: no further phase
            with self.assertRaises(RuntimeError):
                fresh.Validate()
        print("BE_REFUSALS")


if __name__ == '__main__':
    unittest.main()
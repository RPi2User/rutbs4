import unittest

# Module imports
from backend.Checksum import Checksum, ChecksumState, ChecksumType
from backend.Command import Command
from backend.File import File, FileState, FilePath

class UT_File(unittest.TestCase):

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
            str(f)      # TODO Currently deletion is blocking so an external refresh is necessary

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

if __name__ == '__main__':
    unittest.main()
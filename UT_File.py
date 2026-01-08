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
    F_2MIB: str = "./testing/file/2mib.file"
    F_TOUCH: str = "./testing/file/delete.me"

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

"""
    def test_default(self):
        file: File = File(1, self.F_2MIB)
        file.cksum.validate(self.SHA256)
        file.cksum.wait()

        # Object Validation
        self.assertEqual(file.id, 1)
        self.assertEqual(file.size, 2097152)
        self.assertEqual(file.cmd.running, False)

        # Checksum Validation
        self.assertEqual(file.cksum.validation_target, self.SHA256)
        self.assertEqual(file.cksum.state, ChecksumState.IDLE)
        self.assertEqual(file.cksum.value, self.SHA256)

        # testing json capabilities with this simple test:
        # str(file):            file -> json-convert -> string
        # str(json.loads(...)): string -> json-validation -> str(result)
        # len(file_json) != 0 and no Exception
        file_json: str = str(json.loads(str(file)))
        self.assertNotEqual(len(file_json), 0)

    def test_touch(self):
        file: File = File(2, self.F_TOUCH, True)

        # Object Validation
        self.assertEqual(file.id, 2)
        self.assertEqual(file.size, 0)
        self.assertEqual(file.cmd.running, False)


    def test_touchDelete(self):
        
        #1. check if delete.me is there
        #2. delete delete.me
        
        pass

    def test_check_md5(self) -> None:
        return
        file: File = File(1, "./testing/test_1/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.MD5)
        c.value = self.MD5
        
        file.setChecksum(c)
        file.validateIntegrity()

        file.cksum.wait()
        file._asdict()

        #print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params

        self.assertEqual(file.cksum.validation_target, self.MD5)
        self.assertEqual(file.cksum.state, ChecksumState.IDLE)
        self.assertEqual(file.cksum.value, self.MD5)

    def test_fail_md5(self) -> None:
        return
        file: File = File(1, "./testing/test_1/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.MD5)
        wrong_sum = self.MD5[:-1] + "q"   # add a invalid hex-char
        c.value = wrong_sum
        
        file.setChecksum(c)
        file.validateIntegrity()

        file.cksum.wait()
        file._asdict()

        self.assertEqual(file.cksum.validation_target, wrong_sum)
        self.assertEqual(file.cksum.state, ChecksumState.MISMATCH)
        self.assertEqual(file.cksum.value, self.MD5)

    def test_check_sha256(self) -> None:
        return
        file: File = File(1, "./testing/test_1/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.SHA256)
        c.value = self.SHA256
        
        file.setChecksum(c)
        file.validateIntegrity()

        file.cksum.wait()
        file._asdict()

        self.assertEqual(file.cksum.validation_target, self.SHA256)
        self.assertEqual(file.cksum.state, ChecksumState.IDLE)
        self.assertEqual(file.cksum.value, self.SHA256)


    def test_fail_sha256(self) -> None:
        return
        file: File = File(1, "./testing/test_1/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.SHA256)
        wrong_sum = self.SHA256[:-1] + "q"   # add a invalid hex-char
        c.value = wrong_sum
        
        file.setChecksum(c)
        file.validateIntegrity()

        file.cksum.wait()
        file._asdict()

        self.assertEqual(file.cksum.validation_target, wrong_sum)
        self.assertEqual(file.cksum.state, ChecksumState.MISMATCH)
        self.assertEqual(file.cksum.value, self.SHA256)

"""

if __name__ == '__main__':
    unittest.main()
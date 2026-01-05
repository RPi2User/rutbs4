import unittest

# Module imports
from backend.Checksum import Checksum, ChecksumState, ChecksumType
from backend.Command import Command
from backend.File import File, FileState

class UT_File(unittest.TestCase):

    AA: str = "./testing/touch.test"
    AB: str = "./invalid_dir/invalid_file_name.ee4097576b5b6fbace743b2532eda18b0fe08763ce3611c535534ac3a9208ddc"
    SHA256: str = "ee4097576b5b6fbace743b2532eda18b0fe08763ce3611c535534ac3a9208ddc"
    APPENDIX: str = "The quick brown fox jumps over the lazy dog"
    F_2MIB: str = "./testing/file/2mib.file"
    F_TOUCH: str = "./testing/file/delete.me"

    def test_AA_touch(self)-> None:
        f: File = File(id=1, path=self.AA, createFile=True)

        """
        | Variable          | Type        | Description                                        |
        |-------------------|-------------|----------------------------------------------------|
        | `self.id`         | `int`       | Custom user-defined ID for the file                |
        | `self.path`       | `str`       | Absolute and complete file path                    |
        | `self.name`       | `str`       | File name (derived from path)                      |
        | `self.size`       | `int`       | File size in bytes                                 |
        | `self.parent`     | `str`       | Parent directory of the file                       |
        | `self.cmd`        | `Command`   | Command object for executing subprocesses          |
        | `self.cksum`      | `Checksum`  | Checksum object for file integrity verification    |
        | `self.state`      | `FileState` | Current operational state of the file              |
        | `self.state_msg`  | `List[str]` | Logs and messages corresponding to state or errors |
        """

        try:
            self.assertEqual(f.id, 1)
            self.assertEqual(f.name, self.AA.split('/')[-1])
            self.assertEqual(f.size, 0)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(len(f.state_msg), 0)

            self.assertIsInstance(f.cksum, Checksum)
            self.assertIsInstance(f.cmd, Command)
            self.assertGreater(len(f.path), 0)
            self.assertGreater(len(f.parent), 0)

        except AssertionError:
            f.cmd.quiet = False
            print(f)
            raise

        print("A_TOUCH")

    def test_AB_touchFail(self) -> None:
        # Checks if constructor raises exception when
        # - file not found and createFile := False (default)

        try:
            f: File = File(id=1, path=self.AB, createFile=True)
        except FileNotFoundError:
            self.assertTrue(True)

        print("B_TOUCHFAIL")

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
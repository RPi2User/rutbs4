import unittest
import json

# Module imports
from backend.Checksum import *
from backend.File import File

class UT_Checksum(unittest.TestCase):

    MD5: str = "034665aa051c1fe748ad8982347cb320"
    SHA256: str = "42c497d0b2e97b031c172eb2cbb3e389b7c2355b404a1b7afeefef99cec06baf"

    def test_create_md5(self):
        file: File = File(1, "./testing/testfiles/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.MD5)

        file.setChecksum(c)
        file.createChecksum()
        
        file._asdict()

        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()

        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params

        self.assertEqual(file.cksum.old_value, "CKSUM_CREATED")
        self.assertEqual(file.cksum.mismatch, False)
        
        self.assertEqual(file.cksum.value, self.MD5)


    def test_create_sha256(self):
        file: File = File(1, "./testing/testfiles/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.SHA256)

        file.setChecksum(c)
        file.createChecksum()

        file._asdict()

        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()

        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params

        self.assertEqual(file.cksum.old_value, "CKSUM_CREATED")
        self.assertEqual(file.cksum.mismatch, False)

        self.assertEqual(file.cksum.value, self.SHA256)


    def test_check_md5(self) -> None:
        file: File = File(1, "./testing/testfiles/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.MD5)
        c.value = self.MD5
        
        file.setChecksum(c)
        file.createChecksum()
        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params
        
        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()
        
        self.assertEqual(file.cksum.old_value, "CKSUM_OKAY")
        self.assertEqual(file.cksum.mismatch, False)
        
        self.assertEqual(file.cksum.value, self.MD5)

    def test_fail_md5(self) -> None:
        file: File = File(1, "./testing/testfiles/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.MD5)
        wrong_value: str = self.MD5[:-1] + "z"
        c.value = wrong_value
        
        file.setChecksum(c)
        file.createChecksum()
        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params
        
        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()
        
        self.assertEqual(file.cksum.old_value, wrong_value)
        self.assertEqual(file.cksum.mismatch, True)
        
        self.assertEqual(file.cksum.value, self.MD5)

    def test_check_sha256(self) -> None:
        file: File = File(1, "./testing/testfiles/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.SHA256)
        c.value = self.SHA256
        
        file.setChecksum(c)
        file.createChecksum()
        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params
        
        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()
        
        self.assertEqual(file.cksum.old_value, "CKSUM_OKAY")
        self.assertEqual(file.cksum.mismatch, False)
        
        self.assertEqual(file.cksum.value, self.SHA256)


    def test_fail_sha256(self) -> None:
        file: File = File(1, "./testing/testfiles/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.SHA256)
        wrong_value: str = self.SHA256[:-1] + "z"
        c.value = wrong_value
        
        file.setChecksum(c)
        file.createChecksum()
        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params
        
        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()
        
        self.assertEqual(file.cksum.old_value, wrong_value)
        self.assertEqual(file.cksum.mismatch, True)
        
        self.assertEqual(file.cksum.value, self.SHA256)

if __name__ == '__main__':
    unittest.main()
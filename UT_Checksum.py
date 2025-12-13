import unittest
import json

# Module imports
from backend.Checksum import Checksum, ChecksumState, ChecksumType
from backend.File import File

class UT_Checksum(unittest.TestCase):

    MD5: str = "07f9b8f14c23725624cb0745e24e1f98" # old "034665aa051c1fe748ad8982347cb320"
    SHA256: str = "41057efcb2dd05930ca173d1fcd68ad43c60d5936527e01f8f43c62e184072a0" # old "42c497d0b2e97b031c172eb2cbb3e389b7c2355b404a1b7afeefef99cec06baf"

    def test_create_md5(self):
        file: File = File(1, "./testing/test_1/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.MD5)

        file.setChecksum(c)
        file.createChecksum()
        
        file.cksum.wait()

        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params

        self.assertEqual(file.cksum.state, ChecksumState.IDLE)
        self.assertEqual(file.cksum.value, self.MD5)


    def test_create_sha256(self):
        file: File = File(1, "./testing/test_1/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.SHA256)

        file.setChecksum(c)
        file.createChecksum()

        file.cksum.wait()

        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params

        self.assertEqual(file.cksum.state, ChecksumState.IDLE)
        self.assertEqual(file.cksum.value, self.SHA256)


    def test_check_md5(self) -> None:
        file: File = File(1, "./testing/test_1/test100.raw")
        c: Checksum = Checksum(file.path, ChecksumType.MD5)
        c.value = self.MD5
        
        file.setChecksum(c)
        file.validateIntegrity()

        file.cksum.wait()

        print(json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params

        """
        Traceback (most recent call last):
  File "/home/florian/Nextcloud/gits/rutbs4/UT_Checksum.py", line 51, in test_check_md5
    file.cksum.wait()
  File "/home/florian/Nextcloud/gits/rutbs4/backend/Checksum.py", line 60, in wait
    self.cmd.wait()
  File "/home/florian/Nextcloud/gits/rutbs4/backend/Command.py", line 36, in wait
    self.start()
  File "/home/florian/Nextcloud/gits/rutbs4/backend/Command.py", line 66, in start
    raise ValueError("ERROR: Process cannot be initiated, command string empty")
ValueError: ERROR: Process cannot be initiated, command string empty
        """

        self.assertEqual(file.cksum.target_value, self.MD5)
        self.assertEqual(file.cksum.state, ChecksumState.IDLE)
        self.assertEqual(file.cksum.value, self.MD5)

    def test_fail_md5(self) -> None:
        return
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
        return
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
        return
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
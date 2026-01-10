import unittest

# Module imports
from backend.Checksum import Checksum, ChecksumState, ChecksumType
from backend.File import File, FileState

class UT_Checksum(unittest.TestCase):

    MD5: str            = "07f9b8f14c23725624cb0745e24e1f98"
    MD5_SPOILED: str    = "07f9b8f14c23725624cb0745e24e1___"
    SHA256: str         = "41057efcb2dd05930ca173d1fcd68ad43c60d5936527e01f8f43c62e184072a0"
    SHA256_SPOILED: str = "41057efcb2dd05930ca173d1fcd68ad43c60d5936527e01f8f43c62e18407___"
    SHA512: str         = "bfbce2b251d7c0718f69dfc9693999c5095d23a8e4fed0370673031c563a46deafe02822e22631edcf15fcbbb8861989ed95e3e73d112e3a7f63d828b8aba3f9"
    SHA512_SPOILED: str = "bfbce2b251d7c0718f69dfc9693999c5095d23a8e4fed0370673031c563a46deafe02822e22631edcf15fcbbb8861989ed95e3e73d112e3a7f63d828b8aba___"
    
    PATH: str = "/mnt/daten/testfiles/rutbs4/cksum/test100.raw"
    CONTEXT: str = "/mnt/daten/testfiles/rutbs4"
    SIZE: int = 104857600

    def test_A_create_md5(self):
        file: File = File(1, self.PATH, self.CONTEXT)
        file.cksum.setType(ChecksumType.MD5)

        try:
            self.assertEqual(len(file.cksum.value), 0)

            file.createChecksum()

            self.assertEqual(file.state, FileState.CKSUM_CALC)
            self.assertEqual(len(file.cksum.value), 0)
            self.assertEqual(file.cksum.cmd.filesize, self.SIZE)

            file.wait()

            self.assertEqual(file.state, FileState.IDLE)
            self.assertEqual(file.cksum.state, ChecksumState.IDLE)
            self.assertEqual(file.cksum.value, self.MD5)
        except AssertionError:
            print(file)
            raise

        print(".A_CREATE_MD5")

    def test_B_create_sha256(self):
        file: File = File(1, self.PATH, self.CONTEXT)
        file.createChecksum()

        file.wait()

        try:
            self.assertEqual(file.cksum.state, ChecksumState.IDLE)
            self.assertEqual(file.cksum.value, self.SHA256)
        except AssertionError:
            print(file)
            raise

        print("B_CREATE_SHA256")

    def test_C_create_sha512(self):
        file: File = File(1, self.PATH, self.CONTEXT)
        file.cksum.setType(ChecksumType.SHA512)
        file.createChecksum()

        file.wait()

        try:
            self.assertEqual(file.cksum.state, ChecksumState.IDLE)
            self.assertEqual(file.cksum.value, self.SHA512)
        except AssertionError:
            print(file)
            raise

        print("C_CREATE_SHA512")

    def test_D_validate_md5(self) -> None:
        file: File = File(1, self.PATH, self.CONTEXT)
        file.cksum.setType(ChecksumType.MD5)

        file.validateIntegrity(self.MD5)

        try:
            self.assertEqual(file.state, FileState.VALIDATING)
            self.assertEqual(file.cksum.state, ChecksumState.VALIDATE)

            file.wait()

            self.assertEqual(file.state, FileState.IDLE)
            self.assertEqual(file.cksum.state, ChecksumState.IDLE)

        except AssertionError:
            print(file)
            raise

        print("D_VAL_MD5")

    def test_E_validate_sha256(self) -> None:
        file: File = File(1, self.PATH, self.CONTEXT)

        file.validateIntegrity(self.SHA256)

        try:
            self.assertEqual(file.state, FileState.VALIDATING)
            self.assertEqual(file.cksum.state, ChecksumState.VALIDATE)

            file.wait()

            self.assertEqual(file.state, FileState.IDLE)
            self.assertEqual(file.cksum.state, ChecksumState.IDLE)

        except AssertionError:
            print(file)
            raise

        print("E_VAL_SHA256")

    def test_F_validate_sha512(self) -> None:
        file: File = File(1, self.PATH, self.CONTEXT)
        file.cksum.setType(ChecksumType.SHA512)

        file.validateIntegrity(self.SHA512)

        try:
            self.assertEqual(file.state, FileState.VALIDATING)
            self.assertEqual(file.cksum.state, ChecksumState.VALIDATE)

            file.wait()

            self.assertEqual(file.state, FileState.IDLE)
            self.assertEqual(file.cksum.state, ChecksumState.IDLE)

        except AssertionError:
            print(file)
            raise

        print("F_VAL_SHA512")

    def test_G_valSpoil_md5(self) -> None:
        file: File = File(1, self.PATH, self.CONTEXT)
        file.cksum.setType(ChecksumType.MD5)

        file.validateIntegrity(self.MD5_SPOILED)

        try:
            self.assertEqual(file.state, FileState.VALIDATING)
            self.assertEqual(file.cksum.state, ChecksumState.VALIDATE)

            file.wait()

            self.assertEqual(file.state, FileState.MISMATCH)
            self.assertEqual(file.cksum.state, ChecksumState.MISMATCH)
            self.assertEqual(file.state_msg[0], "[ERROR] Checksum mismatch!")
            self.assertNotEqual(file.cksum.value, file.cksum.validation_target)
            self.assertEqual(file.cksum.value, self.MD5)

        except AssertionError:
            print(file)
            raise

        print("G_SPOIL_MD5")

    def test_H_valSpoil_sha256(self) -> None:
        file: File = File(1, self.PATH, self.CONTEXT)

        file.validateIntegrity(self.SHA256_SPOILED)

        try:
            self.assertEqual(file.state, FileState.VALIDATING)
            self.assertEqual(file.cksum.state, ChecksumState.VALIDATE)

            file.wait()

            self.assertEqual(file.state, FileState.MISMATCH)
            self.assertEqual(file.cksum.state, ChecksumState.MISMATCH)
            self.assertEqual(file.state_msg[0], "[ERROR] Checksum mismatch!")
            self.assertNotEqual(file.cksum.value, file.cksum.validation_target)
            self.assertEqual(file.cksum.value, self.SHA256)

        except AssertionError:
            print(file)
            raise

        print("H_SPOIL_SHA256")

    def test_I_valSpoil_sha512(self) -> None:
        file: File = File(1, self.PATH, self.CONTEXT)
        file.cksum.setType(ChecksumType.SHA512)

        file.validateIntegrity(self.SHA512_SPOILED)

        try:
            self.assertEqual(file.state, FileState.VALIDATING)
            self.assertEqual(file.cksum.state, ChecksumState.VALIDATE)

            file.wait()

            self.assertEqual(file.state, FileState.MISMATCH)
            self.assertEqual(file.cksum.state, ChecksumState.MISMATCH)
            self.assertEqual(file.state_msg[0], "[ERROR] Checksum mismatch!")
            self.assertNotEqual(file.cksum.value, file.cksum.validation_target)
            self.assertEqual(file.cksum.value, self.SHA512)

        except AssertionError:
            print(file)
            raise

        print("I_SPOIL_SHA512")


if __name__ == '__main__':
    unittest.main()
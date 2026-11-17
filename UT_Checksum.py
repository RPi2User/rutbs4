import unittest

# Module imports
from backend.Checksum import ChecksumState, ChecksumType
from backend.File import File, FileState
from backend.Job import Job

class UT_Checksum(unittest.TestCase):

    """_summary_
    File.Validate() creates the checksum if the File has none yet, else it compares to it.
    Tests A:
        - A-C: create MD5 / SHA256 / SHA512
        - D-F: compare to the stored value, match
        - G-I: compare to a spoiled value, mismatch
    Depdencies:
    - openssl, fixture cksum/test100.raw
    """

    MD5: str            = "07f9b8f14c23725624cb0745e24e1f98"
    MD5_SPOILED: str    = "07f9b8f14c23725624cb0745e24e1___"
    SHA256: str         = "41057efcb2dd05930ca173d1fcd68ad43c60d5936527e01f8f43c62e184072a0"
    SHA256_SPOILED: str = "41057efcb2dd05930ca173d1fcd68ad43c60d5936527e01f8f43c62e18407___"
    SHA512: str         = "bfbce2b251d7c0718f69dfc9693999c5095d23a8e4fed0370673031c563a46deafe02822e22631edcf15fcbbb8861989ed95e3e73d112e3a7f63d828b8aba3f9"
    SHA512_SPOILED: str = "bfbce2b251d7c0718f69dfc9693999c5095d23a8e4fed0370673031c563a46deafe02822e22631edcf15fcbbb8861989ed95e3e73d112e3a7f63d828b8aba___"

    PATH: str = "/mnt/daten/testfiles/rutbs4/cksum/test100.raw"
    CONTEXT: str = "/mnt/daten/testfiles/rutbs4"
    SIZE: int = 104857600

    def setUp(self) -> None:
        Job.Stop()
        Job.Flush()

    def tearDown(self) -> None:
        Job.Flush()

    def _file(self, type: ChecksumType, value: str = "") -> File:
        file: File = File(1, self.PATH, self.CONTEXT)
        file.cksum.setType(type)
        file.cksum.value = value
        return file

    def _create(self, type: ChecksumType, expected: str) -> None:
        file: File = self._file(type)
        try:
            self.assertEqual(len(file.cksum.value), 0)

            entry: str = file.Validate()

            self.assertEqual(file.state, FileState.QUEUED)
            self.assertEqual(file.cksum.state, ChecksumState.CREATE)
            self.assertEqual(len(file.cksum.value), 0)
            self.assertEqual(file.cksum.cmd.filesize, self.SIZE)

            self.assertTrue(Job.Wait([entry], 60))

            self.assertEqual(file.state, FileState.IDLE)
            self.assertEqual(file.cksum.state, ChecksumState.IDLE)
            self.assertEqual(file.cksum.value, expected)
        except AssertionError:
            print(file)
            raise

    def _validate(self, type: ChecksumType, stored: str, actual: str) -> None:
        file: File = self._file(type, stored)
        try:
            entry: str = file.Validate()

            self.assertEqual(file.state, FileState.QUEUED)
            self.assertEqual(file.cksum.state, ChecksumState.VALIDATE)
            self.assertTrue(Job.Wait([entry], 60))

            if stored == actual:
                self.assertEqual(file.state, FileState.IDLE)
                self.assertEqual(file.cksum.state, ChecksumState.IDLE)
                self.assertEqual(len(file.state_msg), 0)
            else:
                self.assertEqual(file.state, FileState.MISMATCH)
                self.assertEqual(file.cksum.state, ChecksumState.MISMATCH)
                self.assertEqual(file.state_msg, ["[ERROR] Checksum mismatch!"])
                self.assertNotEqual(file.cksum.value, file.cksum.validation_target)
                self.assertEqual(file.cksum.value, actual)
        except AssertionError:
            print(file)
            raise

    def test_A_create_md5(self):
        self._create(ChecksumType.MD5, self.MD5)
        print(".A_CREATE_MD5")

    def test_B_create_sha256(self):
        self._create(ChecksumType.SHA256, self.SHA256)
        print("B_CREATE_SHA256")

    def test_C_create_sha512(self):
        self._create(ChecksumType.SHA512, self.SHA512)
        print("C_CREATE_SHA512")

    def test_D_validate_md5(self) -> None:
        self._validate(ChecksumType.MD5, self.MD5, self.MD5)
        print("D_VAL_MD5")

    def test_E_validate_sha256(self) -> None:
        self._validate(ChecksumType.SHA256, self.SHA256, self.SHA256)
        print("E_VAL_SHA256")

    def test_F_validate_sha512(self) -> None:
        self._validate(ChecksumType.SHA512, self.SHA512, self.SHA512)
        print("F_VAL_SHA512")

    def test_G_valSpoil_md5(self) -> None:
        self._validate(ChecksumType.MD5, self.MD5_SPOILED, self.MD5)
        print("G_VALSPOIL_MD5")

    def test_H_valSpoil_sha256(self) -> None:
        self._validate(ChecksumType.SHA256, self.SHA256_SPOILED, self.SHA256)
        print("H_VALSPOIL_SHA256")

    def test_I_valSpoil_sha512(self) -> None:
        self._validate(ChecksumType.SHA512, self.SHA512_SPOILED, self.SHA512)
        print("I_VALSPOIL_SHA512")

    def test_J_changeTypeAfterConstruction(self) -> None:
        # used to be a known bug: the Command was built once, in the constructor
        file: File = File(1, self.PATH, self.CONTEXT)
        file.cksum.setType(ChecksumType.MD5)
        self.assertTrue(Job.Wait([file.Validate()], 60))
        self.assertEqual(file.state, FileState.IDLE)    # reading the state takes the result over
        self.assertEqual(file.cksum.value, self.MD5)
        print("J_CHANGE_TYPE")


if __name__ == '__main__':
    unittest.main()

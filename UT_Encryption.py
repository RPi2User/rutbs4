import unittest
import json

# Module imports
from backend.Encryption import *
from backend.File import File
from backend.Checksum import *

class UT_Encryption(unittest.TestCase):

    SHA256: str =   "e4104dda1a72365ab706bb2500dc49534465d3b9e597a16ddc38160e5dda8ea0"
    PATH: str =     "/mnt/daten/testfiles/rutbs4/encryption/test100.raw"
    CONTEXT: str =  "/mnt/daten/testfiles/rutbs4"

    AES128CBC: str = "PUT SHA256 HERE"
    AES256CBC: str = "PUT SHA256 HERE"
    AES128CTR: str = "PUT SHA256 HERE"
    AES256CTR: str = "PUT SHA256 HERE"

    KEY_SHORT: str =    "7b3cb4de93854612e9b376bad4911832"
    KEY_MEDIUM: str =   "9b406f953ba4591ce394f6a88b4bf365cf521b27db932a8fd07231a2a2b2b9be"
    IV: str =           "524121a28c0c9d6282176f99c13798e5"

# --- A KEYGEN ----------------------------------------------------------------

    def test_AA_keygen_short(self):
        k: Key = Key(KeyLength.short)
        try:
            self.assertEqual(len(k.value), k.length.value * 2)
        except AssertionError:
            print(k)
            raise
        print(".AA_KEYGEN_SHORT")

    def test_AB_keygen_medium(self):
        k: Key = Key(KeyLength.medium)
        try:
            self.assertTrue(len(k.value), k.length.value * 2)
        except AssertionError:
            print(k)
            raise
        print("AB_KEYGEN_MEDIUM")

# --- B ENCRYPTION ------------------------------------------------------------

    def test_BA_enc_aes128cbc(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)

        try:
            self.assertIsInstance(f.encryption_scheme, File)
        except AssertionError:
            print(f)
            raise

        print("BA_ENC_AES128CBC")

    def test_BB_enc_aes128ctr(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)

        try:
            self.assertIsInstance(f.encryption_scheme, Encryption)
        except AssertionError:
            print(f)
            raise

        print("BB_ENC_AES128CTR")

    def test_BC_enc_aes256cbc(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)

        try:
            self.assertIsInstance(f.encryption_scheme, Encryption)
        except AssertionError:
            print(f)
            raise

        print("BC_ENC_AES256CBC")

    def test_BD_enc_aes256ctr(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)

        try:
            self.assertIsInstance(f.encryption_scheme, Encryption)
        except AssertionError:
            print(f)
            raise

        print("BD_ENC_AES256CTR")

"""

    def test_default(self):
        k: Key = Key() # create key
        e: Encryption = Encryption(k)
        path: str = "./testing/testfiles/test100.raw"
        path_enc: str = "./testing/testfiles/test100.raw.crypt"

        # --- File Init + Checksum
        file: File = File(1, path)
        file = self._checkChecksum(file, self.SHA256)
        # ----------------------------------------------------------


        # --- Encrypt target and re-check Checksum
        file.encrypt(e)

        while file.encryption_scheme.state == E_State.ENCRYPT:
            file._asdict()  # poll status as long as the encryption runs

        file.cksum.file_path = file.path     # refresh path var to path + ".crypt"
        self._checkChecksum(file, self.SHA256, True)
        file.path = "./testing/testfiles/test100.raw"
        file.remove()
        # ----------------------------------------------------------

        # --- Decrypt File
        file: File = File(1, path_enc)
        file.decrypt(e)
        file.encryption_scheme.cmd.wait()

        while file.encryption_scheme.state == E_State.DECRYPT:
            file._asdict()  # poll status as long as the decryption runs

        file.cksum.file_path = file.path    #TODO migrate this into file.encrypt() / file.decrypt()
        self._checkChecksum(file, self.SHA256)

        print(file)
        



    def _checkChecksum(self, file: File, value: str, inverse: bool = False) -> File:
        c: Checksum = Checksum(file.path, value=value)
        file.setChecksum(c)
        file.validateIntegrity()

        file.cksum.wait()

        self.assertEqual(file.cksum.validation_target, value)
        if inverse:
            self.assertEqual(file.cksum.state, ChecksumState.MISMATCH)
            self.assertNotEqual(file.cksum.value, value)
        else:
            self.assertEqual(file.cksum.state, ChecksumState.IDLE)
            self.assertEqual(file.cksum.value, value)
        return file

"""

if __name__ == '__main__':
    unittest.main()
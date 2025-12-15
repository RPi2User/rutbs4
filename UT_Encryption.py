import unittest
import json

# Module imports
from backend.Encryption import *
from backend.File import File
from backend.Checksum import *

class UT_Encryption(unittest.TestCase):

    SHA256: str = "42c497d0b2e97b031c172eb2cbb3e389b7c2355b404a1b7afeefef99cec06baf"

    def test_enc_keygen_short(self):
        k: Key = Key(KeyLength.short)
        self.assertEqual(len(k.value), k.length.value * 2)

    def test_enc_keygen_medium(self):
        k: Key = Key(KeyLength.medium)
        self.assertTrue(len(k.value), k.length.value * 2)

    def test_default(self):
        k: Key = Key() # create key
        e: Encryption = Encryption(k)

        # --- File Init + Checksum
        file: File = File(1, "./testing/testfiles/test100.raw")
        file = self._checkChecksum(file, self.SHA256)
        # ----------------------------------------------------------


        # --- Encrypt target and re-check Checksum
        file.encrypt(e)

        while file.encryption_scheme.state == E_State.ENCRYPT:
            file._asdict()  # poll status as long as the encryption runs

        file.cksum.file_path = file.path     # refresh path var to path + ".crypt"
        self._checkChecksum(file, self.SHA256, True)
        # ----------------------------------------------------------

        # --- Decrypt File
        file.decrypt(e)

        while file.encryption_scheme.state == E_State.DECRYPT:
            file._asdict()  # poll status as long as the decryption runs

        file.cksum.file_path = file.path    #TODO migrate this into file.encrypt() / file.decrypt()
        self._checkChecksum(file, self.SHA256)
        
    def test_all(self) -> None:
        sha256: str = "a1a5c4ca77b72f457ebaa9e8d7231ed488b021c2a886b6e14715b1da5684b3cc"
        k: Key = Key() # create key
        e: Encryption = Encryption(k)
        result: dict = {}

        # --- File Init + Checksum
        file: File = File(1, "./testing/testfiles/test100_all.raw")
        file = self._checkChecksum(file, sha256)
        # ----------------------------------------------------------


        for mode in E_Mode:
            e.mode = mode
            print("Testing Encryption: " + e.mode.name)
            # --- ENCRYPT
            file.encrypt(e)
            while file.encryption_scheme.state == E_State.ENCRYPT:
                file._asdict()  # poll status as long as the encryption runs
            file.cksum.file_path = file.path     # refresh path var to path + ".crypt"
            self._checkChecksum(file, sha256, True)
            # ----------------------------------------------------------

            # --- DECRYPT
            file.decrypt(e)
            while file.encryption_scheme.state == E_State.DECRYPT:
                file._asdict()  # poll status as long as the decryption runs
            file.cksum.file_path = file.path
            self._checkChecksum(file, sha256)

            result.update({mode.name: file._asdict()})

        print("\n\"RESULT\": " + json.dumps(result, indent=2) + "\n")

    def _checkChecksum(self, file: File, value: str, inverse: bool = False) -> File:
        c: Checksum = Checksum(file.path, ChecksumType.SHA256)
        c.value = value
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

if __name__ == '__main__':
    unittest.main()
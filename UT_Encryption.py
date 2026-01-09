import unittest
import json

# Module imports
from backend.Encryption import *
from backend.File import File
from backend.Checksum import *

class UT_Encryption(unittest.TestCase):

    SHA256: str = "e4104dda1a72365ab706bb2500dc49534465d3b9e597a16ddc38160e5dda8ea0"

    def test_AA_keygen_short(self):
        k: Key = Key(KeyLength.short)
        try:
            self.assertEqual(len(k.value), k.length.value * 2)
        except AssertionError:
            print(k)
            raise
        print(".A_KEYGEN_SHORT")

    def test_AB_keygen_medium(self):
        k: Key = Key(KeyLength.medium)
        try:
            self.assertTrue(len(k.value), k.length.value * 2)
        except AssertionError:
            print(k)
            raise
        print("B_KEYGEN_MEDIUM")

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
        

    def test_all(self) -> None:
        return
        sha256: str = "7afa7a26406d770d57864267f7ea57395b09ffb1d0773a289c7ee23851d6730f"
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
import unittest
import json

# Module imports
from backend.Encryption import *
from backend.File import File, FileState
from backend.Checksum import *

class UT_Encryption(unittest.TestCase):

    SHA256: str =   "41057efcb2dd05930ca173d1fcd68ad43c60d5936527e01f8f43c62e184072a0"
    PATH: str =     "/mnt/daten/testfiles/rutbs4/encryption/test100.raw"
    CONTEXT: str =  "/mnt/daten/testfiles/rutbs4"

    KEY_SHORT: str =    "7b3cb4de93854612e9b376bad4911832"
    KEY_MEDIUM: str =   "9b406f953ba4591ce394f6a88b4bf365cf521b27db932a8fd07231a2a2b2b9be"
    IV: str =           "524121a28c0c9d6282176f99c13798e5"

# --- A KEYGEN ----------------------------------------------------------------

    def test_AA_keygen_short(self):
        k: Key = Key(KeyLength.short)
        try:
            self.assertEqual(k.length.name, "short")
            self.assertEqual(len(k.value), k.length.value * 2)
            self.assertEqual(len(k.iv), 32)
            self.assertNotEqual(k.value, k.iv)
        except AssertionError:
            print(k)
            raise
        print(".AA_KEYGEN_SHORT")

    def test_AB_keygen_medium(self):
        k: Key = Key(KeyLength.medium)
        try:
            self.assertEqual(k.length.name, "medium")
            self.assertTrue(len(k.value), k.length.value * 2)
            self.assertEqual(len(k.iv), 32)
            self.assertNotEqual(k.value, k.iv)
        except AssertionError:
            print(k)
            raise
        print("AB_KEYGEN_MEDIUM")

# --- B ENCRYPTION ------------------------------------------------------------

    def test_BA_enc_aes128cbc(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)
        k: Key = Key(KeyLength.short)
        k.value = self.KEY_SHORT
        k.iv = self.IV

        try:
            e: Encryption = Encryption(k, E_Mode.AES128CBC)
            e.keepOrig = False
            e.cmd.filesize = f.size
            f.encryption_scheme = e

            self.assertEqual(f.encryption_scheme, e)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

            # 1. Encrypt File
            f.encrypt()
            self.assertEqual(f.state, FileState.ENCRYPT)
            self.assertEqual(f.encryption_scheme.state, E_State.ENCRYPT)
            self.assertEqual(f.encryption_scheme.targetPath, self.PATH + ".crypt")
            f.wait()

            # 2. Check if Checksum indeed invalid
            f.validateIntegrity(self.SHA256)
            f.wait()

            self.assertEqual(len(f.state_msg), 1)
            self.assertEqual(f.state, FileState.MISMATCH)
            self.assertEqual(f.state_msg[0], "[ERROR] Checksum mismatch!")
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

            # 3. Decrypt File
            f.state = FileState.IDLE    # state machine will block further operations
            f.decrypt()
            self.assertEqual(f.state, FileState.DECRYPT)
            self.assertEqual(f.encryption_scheme.state, E_State.DECRYPT)
            self.assertEqual(f.encryption_scheme.targetPath, self.PATH)
            f.wait()

            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)
            self.assertEqual(len(f.state_msg), 1)

            # 4. Check if we restored the correct file :3
            f.validateIntegrity(self.SHA256)
            f.wait()

            self.assertEqual(len(f.state_msg), 1)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

        except AssertionError:
            print(f)
            raise

        print("BA_AES128CBC")

    def test_BB_aes128ctr(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)
        k: Key = Key(KeyLength.short)
        k.value = self.KEY_SHORT
        k.iv = self.IV

        try:
            e: Encryption = Encryption(k, E_Mode.AES128CTR)
            e.keepOrig = False
            e.cmd.filesize = f.size
            f.encryption_scheme = e

            # 1. Encrypt File
            f.encrypt()
            f.wait()

            # 2. Check if Checksum indeed invalid
            f.validateIntegrity(self.SHA256)
            f.wait()

            self.assertEqual(len(f.state_msg), 1)
            self.assertEqual(f.state, FileState.MISMATCH)
            self.assertEqual(f.state_msg[0], "[ERROR] Checksum mismatch!")
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

            # 3. Decrypt File
            f.state = FileState.IDLE    # state machine will block further operations
            f.decrypt()
            f.wait()

            # 4. Check if we restored the correct file :3
            f.validateIntegrity(self.SHA256)
            f.wait()

            self.assertEqual(len(f.state_msg), 1)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

        except AssertionError:
            print(f)
            raise

        print("BB_AES128CTR")

    def test_BC_aes256cbc(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)
        k: Key = Key(KeyLength.short)
        k.value = self.KEY_SHORT
        k.iv = self.IV

        try:
            e: Encryption = Encryption(k, E_Mode.AES256CBC)
            e.keepOrig = False
            e.cmd.filesize = f.size
            f.encryption_scheme = e

            # 1. Encrypt File
            f.encrypt()
            f.wait()

            # 2. Check if Checksum indeed invalid
            f.validateIntegrity(self.SHA256)
            f.wait()

            self.assertEqual(len(f.state_msg), 1)
            self.assertEqual(f.state, FileState.MISMATCH)
            self.assertEqual(f.state_msg[0], "[ERROR] Checksum mismatch!")
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

            # 3. Decrypt File
            f.state = FileState.IDLE    # state machine will block further operations
            f.decrypt()
            f.wait()

            # 4. Check if we restored the correct file :3
            f.validateIntegrity(self.SHA256)
            f.wait()

            self.assertEqual(len(f.state_msg), 1)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

        except AssertionError:
            print(f)
            raise

        print("BC_AES256CBC")

    def test_BD_aes256ctr(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)
        k: Key = Key(KeyLength.short)
        k.value = self.KEY_SHORT
        k.iv = self.IV

        try:
            e: Encryption = Encryption(k, E_Mode.AES256CTR)
            e.keepOrig = False
            e.cmd.filesize = f.size
            f.encryption_scheme = e

            # 1. Encrypt File
            f.encrypt()
            f.wait()

            # 2. Check if Checksum indeed invalid
            f.validateIntegrity(self.SHA256)
            f.wait()

            self.assertEqual(len(f.state_msg), 1)
            self.assertEqual(f.state, FileState.MISMATCH)
            self.assertEqual(f.state_msg[0], "[ERROR] Checksum mismatch!")
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

            # 3. Decrypt File
            f.state = FileState.IDLE    # state machine will block further operations
            f.decrypt()
            f.wait()

            # 4. Check if we restored the correct file :3
            f.validateIntegrity(self.SHA256)
            f.wait()

            self.assertEqual(len(f.state_msg), 1)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

        except AssertionError:
            print(f)
            raise

        print("BD_AES256CTR")

    def test_CA_ALL_MEDIUM(self) -> None:
        f: File = File(1, self.PATH, self.CONTEXT)
        k: Key = Key(KeyLength.medium)
        k.value = self.KEY_MEDIUM
        k.iv = self.IV
        result: dict = {}

        for scheme in E_Mode:

            try:
                e: Encryption = Encryption(k, scheme)
                e.keepOrig = False
                e.cmd.filesize = f.size
                f.encryption_scheme = e

                # 1. Encrypt File
                f.encrypt()
                f.wait()

                # 2. Check if Checksum indeed invalid
                f.createChecksum()
                f.wait()

                self.assertNotEqual(f.cksum.value, self.SHA256)
                self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

                # 3. Decrypt File
                f.state = FileState.IDLE    # state machine will block further operations
                f.decrypt()
                f.wait()

                # 4. Check if we restored the correct file :3
                f.validateIntegrity(self.SHA256)
                f.wait()

                self.assertEqual(len(f.state_msg), 0)
                self.assertEqual(f.state, FileState.IDLE)
                self.assertEqual(f.encryption_scheme.state, E_State.IDLE)

            except AssertionError:
                print(f)
                raise

            result.update({scheme.name: f._asdict()})
        #print(json.dumps(result, indent=2))
        print("CA_ALL_MEDIUM")


if __name__ == '__main__':
    unittest.main()
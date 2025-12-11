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
        c: Checksum = Checksum(file.path, ChecksumType.SHA256)
        c.value = self.SHA256
        
        file.setChecksum(c)
        file.createChecksum()

        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()

        self.assertEqual(file.cksum.old_value, "CKSUM_OKAY")
        print("[CKSUM]" + json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params
        self.assertEqual(file.cksum.mismatch, False)
        
        self.assertEqual(file.cksum.value, self.SHA256)
        # ----------------------------------------------------------


        # --- Encrypt target and re-check Checksum
        file.encrypt(e)

        while file.encryption_scheme.state == E_State.ENCRYPT:
            file._asdict()  # poll status as long as the encryption runs

        file.cksum.file_path = file.path     # refresh path var to path + ".crypt"
        file.createChecksum()

        print("[ENCRYPT]" + json.dumps(file._asdict(), indent=2))    # this triggers a refresh of all params

        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()

        self.assertEqual(file.cksum.old_value, self.SHA256)
        self.assertEqual(file.cksum.mismatch, True)

        self.assertNotEqual(file.cksum.value, self.SHA256)
        # ----------------------------------------------------------

        # --- Decrypt File
        file.decrypt(e)

        while file.encryption_scheme.state == E_State.DECRYPT:
            file._asdict()  # poll status as long as the decryption runs

        file.cksum.file_path = file.path    #TODO migrate this into file.encrypt() / file.decrypt()
        file.createChecksum()

        file._asdict()  # Return object to caller-API (in this case -> None)

        if len(file.cksum.value) == 0:
            file.cksum.cmd.wait()

        self.assertNotEqual(file.cksum.old_value, self.SHA256) # still has cksum of encrypted file
        self.assertEqual(file.cksum.mismatch, True)

        self.assertEqual(file.cksum.value, self.SHA256) # THIS IS THE IMPORTANT STEP

if __name__ == '__main__':
    unittest.main()
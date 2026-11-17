import os
import unittest

# Module imports
from backend.Encryption import *
from backend.File import File, FileState
from backend.Checksum import *
from backend.Job import Job

class UT_Encryption(unittest.TestCase):

    """_summary_
    Tests A:
        - AA-AB: key generation
        - BA-BD: round trip per mode: Validate, Encrypt, Decrypt, Validate
        - CA:    round trip for every mode
        - DA-DB: wrong key shows as a mismatch (CTR) or as an error (CBC)
    The original is never touched: Encrypt() writes `<path>.crypt`, Decrypt() writes `<path>.restored`.
    Depdencies:
    - openssl, fixture encryption/test100.raw
    """

    def setUp(self) -> None:
        Job.Stop()
        Job.Flush()

    def tearDown(self) -> None:
        Job.Flush()
        for leftover in [self.PATH + ".crypt", self.PATH + ".restored"]:
            if os.path.exists(leftover):
                os.remove(leftover)

    def _wait(self, *entries: str) -> None:
        self.assertTrue(Job.Wait([e for e in entries if e], 120))      # "" = a phase that had nothing to do

    SHA256: str =   "ceba3a61162967a79033e029e24b19f21a5ebeff6b512ac9847cf13f7dc56669"
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

    def _file(self, mode: E_Mode, key: str, iv: str, length: KeyLength) -> File:
        f: File = File(1, self.PATH, self.CONTEXT)
        k: Key = Key(length)
        k.value = key
        k.iv = iv
        f.encryption_scheme = Encryption(k, mode)
        return f

    def _roundtrip(self, f: File) -> None:
        mode: E_Mode = f.encryption_scheme.mode
        crypt: str = self.PATH + ".crypt"
        restored: str = self.PATH + ".restored"

        try:
            # 1. checksum of the plain file
            self._wait(f.Validate())
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.cksum.value, self.SHA256)

            # 2. Encrypt: a new file next to the original, the File itself stays the original
            entry: str = f.Encrypt()
            if mode is E_Mode.NONE:
                self.assertEqual(entry, "")     # nothing to do, nothing queued
            else:
                self.assertEqual(f.state, FileState.QUEUED)
                self.assertEqual(f.encryption_scheme.state, E_State.ENCRYPT)
                self.assertEqual(f.encryption_scheme.targetPath, crypt)
            self._wait(entry)
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)
            self.assertEqual(f.path.path, self.PATH)

            if mode is not E_Mode.NONE:
                self.assertTrue(os.path.exists(crypt))
                other: File = File(2, crypt, self.CONTEXT)  # is it really not the plain file anymore?
                self._wait(other.Validate())
                self.assertEqual(other.state, FileState.IDLE)
                self.assertNotEqual(other.cksum.value, self.SHA256)

            # 3. Decrypt into a new file and check that we restored the correct file :3
            self._wait(f.Decrypt(restored))
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(f.encryption_scheme.state, E_State.IDLE)
            self.assertEqual(f.where, restored if mode is not E_Mode.NONE else self.PATH)

            self._wait(f.Validate())    # compares to the stored checksum
            self.assertEqual(f.state, FileState.IDLE)
            self.assertEqual(len(f.state_msg), 0)
            if mode is not E_Mode.NONE:
                self.assertTrue(os.path.exists(restored))
        except AssertionError:
            print(f)
            raise

    def test_BA_enc_aes128cbc(self) -> None:
        self._roundtrip(self._file(E_Mode.AES128CBC, self.KEY_SHORT, self.IV, KeyLength.short))
        print("BA_AES128CBC")

    def test_BB_aes128ctr(self) -> None:
        self._roundtrip(self._file(E_Mode.AES128CTR, self.KEY_SHORT, self.IV, KeyLength.short))
        print("BB_AES128CTR")

    def test_BC_aes256cbc(self) -> None:
        self._roundtrip(self._file(E_Mode.AES256CBC, self.KEY_SHORT, self.IV, KeyLength.short))
        print("BC_AES256CBC")

    def test_BD_aes256ctr(self) -> None:
        self._roundtrip(self._file(E_Mode.AES256CTR, self.KEY_SHORT, self.IV, KeyLength.short))
        print("BD_AES256CTR")

    def test_CA_ALL_MEDIUM(self) -> None:
        for scheme in E_Mode:
            self._roundtrip(self._file(scheme, self.KEY_MEDIUM, self.IV, KeyLength.medium))
            self.tearDown()     # next mode starts without the files of the last one
        print("CA_ALL_MEDIUM")

# --- D WRONG KEY -------------------------------------------------------------

    def _wrongKey(self, mode: E_Mode) -> File:
        f: File = self._file(mode, self.KEY_MEDIUM, self.IV, KeyLength.medium)
        self._wait(f.Validate())
        self._wait(f.Encrypt())
        f.encryption_scheme.key.value = "00" * 32
        self._wait(f.Decrypt(self.PATH + ".restored"))
        return f

    def test_DA_wrongKeyCTR(self) -> None:
        # CTR has no padding check, it decrypts to garbage and only the checksum notices
        f: File = self._wrongKey(E_Mode.AES256CTR)
        self.assertEqual(f.state, FileState.IDLE)

        self._wait(f.Validate())
        self.assertEqual(f.state, FileState.MISMATCH)
        self.assertEqual(f.state_msg, ["[ERROR] Checksum mismatch!"])
        with self.assertRaises(RuntimeError):
            f.Encrypt()     # MISMATCH is final
        print("DA_WRONG_KEY_CTR")

    def test_DB_wrongKeyCBC(self) -> None:
        # CBC notices the wrong key by itself ("bad decrypt"), so the phase fails
        f: File = self._wrongKey(E_Mode.AES256CBC)
        self.assertEqual(f.state, FileState.ERROR)
        self.assertEqual(f.state_msg, ["[ERROR] DECRYPT failed or was not run"])
        print("DB_WRONG_KEY_CBC")


if __name__ == '__main__':
    unittest.main()

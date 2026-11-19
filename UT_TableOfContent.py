import json
import os
import re
import tempfile
import unittest

# Module imports
from backend.Checksum import ChecksumType
from backend.Encryption import E_Mode
from backend.Folder import Folder
from backend.TableOfContent import TableOfContent, TOC_Header, TOC_State, TOC_WrongPassphrase
from backend.Tape import Tape
from backend.TapeDrive import TapeDrive
from backend.Version import Version


class UT_TableOfContent(unittest.TestCase):

    """_summary_
    Tests A:
        - AA-AB: Header carries version, fingerprint, state and no key material
        - B:     seal() -> open() round trip, key and IV of every file come back
        - C:     wrong passphrase, empty passphrase, foreign document
        - D:     header is readable without passphrase, state can change for the trailing TOC
        - E:     TOC directory
    Depdencies:
    - openssl
    """

    PASSPHRASE: str = "correct horse battery staple"

    def _toc(self, tmp: str) -> TableOfContent:
        src: str = os.path.join(tmp, "src")
        os.makedirs(os.path.join(src, "sub"))
        for name in ["a.txt", "b b.txt", "sub/c.txt"]:
            with open(os.path.join(src, name), "w") as f:
                f.write("data " + name)

        folder: Folder = Folder(src, ChecksumType.SHA256, E_Mode.AES256CBC)
        return TableOfContent(folder, TOC_Header(self._drive(tmp), threadCount=2))

    def _drive(self, tmp: str) -> TapeDrive:
        tape_path: str = os.path.join(tmp, "faketape.bin")
        open(tape_path, "wb").close()
        td: TapeDrive = TapeDrive(path=tape_path, generic_path="", drive_override=True)
        td.tapeOverride(Tape("3800", td.generic_path))
        return td

    def test_AA_headerFields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            header: dict = self._toc(tmp).header._asdict()

            self.assertEqual(header["format"], "rutbs")
            self.assertEqual(header["version"], Version.word())
            self.assertEqual(header["state"], "IDLE")
            self.assertEqual(header["threadCount"], 2)
            self.assertEqual(header["blocksize"], "256K")
            self.assertEqual(header["body_cipher"], "AES256CTR")
            self.assertEqual(header["tape"]["lto-version"], "LTO_3")
            self.assertRegex(header["fingerprint"], r"^[0-9a-f-]{36}$")

    def test_AB_fingerprintCanBeGiven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            self.assertEqual(TOC_Header(td, 1, fingerprint="abc").fingerprint, "abc")
            with self.assertRaises(ValueError):
                TOC_Header(td, 1, bodyCipher=E_Mode.NONE)

    def test_B_roundTrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toc: TableOfContent = self._toc(tmp)
            text: str = toc.seal(self.PASSPHRASE)

            keys: list = [(f.encryption_scheme.key.value, f.encryption_scheme.key.iv) for f in toc.folder.files]
            self.assertEqual(len(keys), 3)

            # nothing secret in the clear text part
            for value, iv in keys:
                self.assertNotIn(value, json.dumps(json.loads(text)["header"]))
            self.assertNotIn("a.txt", text)    # file names are in the body, too

            opened: dict = TableOfContent.open(text, self.PASSPHRASE)
            files: list = opened["body"]["folder"]["files"]
            self.assertEqual([f["path"]["relPath"] for f in files], ["a.txt", "b b.txt", "sub/c.txt"])
            self.assertEqual([f["id"] for f in files], [1, 2, 3])
            restored: list = [(f["encryption"]["key"]["value"], f["encryption"]["key"]["iv"]) for f in files]
            self.assertEqual(sorted(restored), sorted(keys))

    def test_C_wrongPassphrase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toc: TableOfContent = self._toc(tmp)
            text: str = toc.seal(self.PASSPHRASE)

            with self.assertRaises(TOC_WrongPassphrase):
                TableOfContent.open(text, "wrong")
            with self.assertRaises(ValueError):
                toc.seal("")
            with self.assertRaises(ValueError):
                TableOfContent.readHeader('{"header": {"format": "tbk3"}}')

    def test_D_headerWithoutPassphraseAndTrailingState(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toc: TableOfContent = self._toc(tmp)
            first: str = toc.seal(self.PASSPHRASE)
            self.assertEqual(TableOfContent.readHeader(first)["state"], "IDLE")

            toc.header.state = TOC_State.COMPLETE
            trailing: str = toc.seal(self.PASSPHRASE)
            self.assertEqual(TableOfContent.readHeader(trailing)["state"], "COMPLETE")
            self.assertEqual(TableOfContent.readHeader(trailing)["fingerprint"],
                             TableOfContent.readHeader(first)["fingerprint"])
            self.assertNotEqual(first, trailing)    # new salt every time

    def test_E_tocDirectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toc: TableOfContent = self._toc(tmp)
            with self.assertRaises(ValueError):
                toc.store(tmp)      # not sealed yet

            text: str = toc.seal(self.PASSPHRASE)
            path: str = toc.store(tmp)

            self.assertRegex(os.path.basename(path), r"^\d{8}_\d{6}_" + toc.header.fingerprint + r"\.json$")
            with open(path) as f:
                self.assertEqual(f.read(), text)
            with open(path) as f:
                stored: dict = TableOfContent.open(f.read(), self.PASSPHRASE)
            self.assertEqual(stored["header"]["fingerprint"], toc.header.fingerprint)


if __name__ == "__main__":
    unittest.main()

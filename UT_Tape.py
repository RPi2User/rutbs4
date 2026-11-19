import json
import os
import tempfile
import unittest

# Module imports
from backend.CartridgeMemory import CartridgeMemory
from backend.TD_Pool import TD_Pool
from backend.Tape import E_LTOv, E_Tape, Tape
from backend.Version import Version

class UT_Tape(unittest.TestCase):

    """_summary_
    Tests A to D: the Tape itself.
    Tests E to J: its CartridgeMemory (the chip), with small scripts in place of sg_read_attr / sg_write_attr:
        - E: parsing the hex dump of an answer: ASCII and text attributes, padding, binary ones ignored
        - F: a chip without our attributes, a cut-off answer
        - G: reading through the tool; a failing tool leaves the fields empty and sets the error
        - H: format() writes name, version and a NEW fingerprint, the fields follow when the write succeeded
        - I: a failed write keeps the old values
        - J: (real drive) the chip of the loaded tape was read when the drive started, only with RUTBS_TEST_TAPE=1; never writes
        - EB: the tape keeps the generic device of its drive, only a loaded tape gets a chip to read
    """

    AA: str    = "3810" # LTO3, Tape, no WP
    AB_WP: str = "8890" # LTO8, Tape, WP enabled
    AC_CS: str = "0810" # NONE, Tape, no WP

    def test_AA_sanity(self)-> None:
        "LTO3 Tape with no Write Protect"
        t: Tape = Tape(self.AA, "")

        try:
            self.assertEqual(t.lto_version, E_LTOv.LTO_3)
            self.assertEqual(t.native_capacity, 300000000000)
            self.assertEqual(t.write_protect, False)
            self.assertEqual(t.begin_of_tape, False)
            self.assertEqual(t.state, E_Tape.ONLINE)
            self.assertEqual(t.blocksize, "256K")

            self.assertIsInstance(t, Tape)
            self.assertIsInstance(t.lto_version, E_LTOv)
            self.assertIsInstance(t.state, E_Tape)

        except AssertionError:
            print(t)
            raise

        print(".A_TAPE")

    def test_AB_WriteProtect(self) -> None:
        "LTO8 Tape with Write Protect enabled, blocksize of 1GiB"
        t: Tape = Tape(self.AB_WP, "", "1G")

        try:
            self.assertEqual(t.lto_version, E_LTOv.LTO_8)
            self.assertEqual(t.native_capacity, 12000000000000)
            self.assertEqual(t.write_protect, True)
            self.assertEqual(t.state, E_Tape.WRITE_PROTECT)
            self.assertEqual(t.blocksize, "1G")

            self.assertIsInstance(t, Tape)
            self.assertIsInstance(t.lto_version, E_LTOv)
            self.assertIsInstance(t.state, E_Tape)

        except AssertionError:
            print(t)
            raise

        print("B_WRITEPROTECT")

    def test_AC_Custom(self) -> None:
        "Custom Tape with no WP and default Blocksize"
        t: Tape = Tape(self.AC_CS, "")
        t.native_capacity = 512

        try:
            self.assertEqual(t.lto_version, E_LTOv.NONE)
            self.assertEqual(t.native_capacity, 512)
            self.assertEqual(t.write_protect, False)
            self.assertEqual(t.state, E_Tape.ONLINE)
            self.assertEqual(t.blocksize, "256K")

            self.assertIsInstance(t, Tape)
            self.assertIsInstance(t.lto_version, E_LTOv)
            self.assertIsInstance(t.state, E_Tape)

        except AssertionError:
            print(t)
            raise

        print("C_CUSTOM")

    def test_AD_UnknownCapacity(self) -> None:
        "LTO11 has no known capacity yet, the tape is still usable"
        t: Tape = Tape("b810", "")

        self.assertEqual(t.lto_version, E_LTOv.LTO_11)
        self.assertEqual(t.native_capacity, 0)
        self.assertEqual(t.state, E_Tape.ONLINE)
        print("D_UNKNOWN_CAPACITY")

    # === CartridgeMemory =====================================================

    @staticmethod
    def _attr(attrId: int, fmt: int, value: bytes) -> bytes:
        return attrId.to_bytes(2, "big") + bytes([fmt]) + len(value).to_bytes(2, "big") + value

    @classmethod
    def _dump(cls, attributes: bytes, cut: int = 0) -> str:
        """An answer of READ ATTRIBUTE as `sg_read_attr -H` prints it: offset, 16 bytes a line, a gap after 8."""
        data: bytes = len(attributes).to_bytes(4, "big") + attributes
        data = data[:len(data) - cut]
        lines: list = []
        for off in range(0, len(data), 16):
            row: bytes = data[off:off + 16]
            cells: str = " ".join("%02x" % b for b in row[:8]) + ("  " + " ".join("%02x" % b for b in row[8:]) if len(row) > 8 else "")
            lines.append(" %02x     %s" % (off, cells))
        return "\n".join(lines) + "\n"

    def _chip(self, fingerprint: str = "11111111-2222-3333-4444-555555555555") -> bytes:
        """What a drive answers: a read-only binary attribute, then ours padded like the drive pads them."""
        return (self._attr(0x0000, 0x80, (4096).to_bytes(8, "big")) +
                self._attr(0x0401, 0x81, b"SERIAL".ljust(32)) +
                self._attr(0x0801, 0x01, b"rutbs".ljust(32)) +
                self._attr(0x0802, 0x01, b"4000".ljust(8)) +
                self._attr(0x0803, 0x02, fingerprint.encode().ljust(160, b"\0")))

    def _tool(self, directory: str, name: str, script: str) -> str:
        path: str = os.path.join(directory, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + script + "\n")
        os.chmod(path, 0o755)
        return path

    def test_EA_ParseAnswer(self) -> None:
        "ASCII and text attributes lose their padding, binary ones and the drive's own are not returned"
        attrs: dict = CartridgeMemory.parse(self._dump(self._chip()).splitlines())
        self.assertEqual(attrs[0x0801], "rutbs")
        self.assertEqual(attrs[0x0802], "4000")
        self.assertEqual(attrs[0x0803], "11111111-2222-3333-4444-555555555555")
        self.assertNotIn(0x0000, attrs)
        print("EA_PARSE")

    def test_FA_EmptyAndCutOff(self) -> None:
        "A chip without our attributes gives empty fields; a cut-off answer is an error, not wrong data"
        with tempfile.TemporaryDirectory() as d:
            fixture: str = os.path.join(d, "answer")
            with open(fixture, "w") as f:
                f.write(self._dump(self._attr(0x0401, 0x81, b"SERIAL".ljust(32))))
            cm: CartridgeMemory = CartridgeMemory("/dev/null", readTool=self._tool(d, "read", "cat " + fixture))
            self.assertEqual((cm.appName, cm.version, cm.fingerprint, cm.error), ("", "", "", ""))

            with open(fixture, "w") as f:
                f.write(self._dump(self._chip(), cut=20))
            cm.read()
            self.assertEqual(cm.fingerprint, "")
            self.assertIn("cut off", cm.error)
        print("FA_EMPTY_CUTOFF")

    def test_GA_Read(self) -> None:
        "Read through the tool; a failing tool (LTO-3 may not know the command) leaves the fields empty"
        with tempfile.TemporaryDirectory() as d:
            fixture: str = os.path.join(d, "answer")
            with open(fixture, "w") as f:
                f.write(self._dump(self._chip()))
            cm: CartridgeMemory = CartridgeMemory("/dev/null", readTool=self._tool(d, "read", "cat " + fixture))
            self.assertEqual(cm.appName, "rutbs")
            self.assertEqual(cm.version, "4.0.0")
            self.assertEqual(cm.fingerprint, "11111111-2222-3333-4444-555555555555")
            self.assertEqual(cm.error, "")

            cm.readTool = self._tool(d, "broken", "echo 'Read attribute command: Illegal request' >&2; exit 1")
            cm.read()
            self.assertEqual(cm.fingerprint, "")
            self.assertIn("Illegal request", cm.error)
        print("GA_READ")

    def test_HA_Format(self) -> None:
        "format() writes name, version and a NEW fingerprint every time; the fields follow the finished write"
        with tempfile.TemporaryDirectory() as d:
            record: str = os.path.join(d, "args")
            cm: CartridgeMemory = CartridgeMemory(writeTool=self._tool(d, "write", 'sleep 0.3; printf "%s\\n" "$@" > ' + record))
            self.assertRaises(ValueError, cm.format)       # no device
            cm.device = "/dev/sgX"

            cm.format()
            self.assertEqual(cm.fingerprint, "")           # still writing
            self.assertRaises(RuntimeError, cm.format)
            assert cm.cmd is not None
            cm.cmd.wait()

            with open(record) as f:
                args: list = f.read().split()
            self.assertEqual(args[:3], ["/dev/sgX", "AppName=rutbs", "AppVersion=%04x" % Version.word()])
            first: str = cm.fingerprint
            self.assertEqual(args[3], "UserLabel=" + first)
            self.assertRegex(first, r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
            self.assertEqual((cm.appName, cm.version, cm.error), ("rutbs", Version.text(), ""))

            cm.format()
            cm.cmd.wait()
            self.assertNotEqual(cm.fingerprint, first)

            out: dict = json.loads(str(cm))
            self.assertEqual(set(out), {"appName", "version", "fingerprint", "error"})
            self.assertEqual(out["fingerprint"], cm.fingerprint)
            print(cm)
        print("HA_FORMAT")

    def test_IA_FormatFails(self) -> None:
        "A failed write keeps the old values and says why"
        with tempfile.TemporaryDirectory() as d:
            cm: CartridgeMemory = CartridgeMemory("/dev/sgX", writeTool=self._tool(d, "write", "exit 0"))
            cm.format()
            assert cm.cmd is not None
            cm.cmd.wait()
            old: str = cm.fingerprint
            self.assertNotEqual(old, "")

            cm.writeTool = self._tool(d, "failing", "echo 'Write attribute: Medium error' >&2; exit 1")
            cm.format()
            cm.cmd.wait()
            self.assertEqual(cm.fingerprint, old)
            self.assertIn("Medium error", cm.error)
        print("IA_FORMAT_FAILS")

    def test_EB_DeviceOfTape(self) -> None:
        "The tape knows the generic device of its drive; only a loaded tape gets a chip to read"
        t: Tape = Tape(self.AA, "/dev/null")
        self.assertEqual(t.generic_path, "/dev/null")
        self.assertEqual(t.cartridgeMemory.device, "/dev/null")
        self.assertEqual(Tape("0000", "/dev/null").cartridgeMemory.device, "")
        print("EB_DEVICE_OF_TAPE")

    def test_JA_RealDrive(self) -> None:
        "Reads the chip of the first drive, writes nothing. Both an answer and an error are a result"
        if os.environ.get("RUTBS_TEST_TAPE") != "1":
            self.skipTest("RUTBS_TEST_TAPE=1 is not set")
        drives: list = TD_Pool().gatherDrives()
        if not drives:
            self.skipTest("no tape drive")
        tape: Tape = drives[0].tape
        self.assertEqual(tape.generic_path, drives[0].generic_path)
        print(tape.cartridgeMemory)
        if tape.state is E_Tape.NO_TAPE:
            self.skipTest("no tape in the drive")
        self.assertEqual(tape.cartridgeMemory.device, tape.generic_path)
        self.assertEqual(tape.cartridgeMemory.error, "")
        self.assertEqual(tape.cartridgeMemory.appName, "rutbs")
        print("JA_REAL_DRIVE")

if __name__ == '__main__':
    unittest.main()
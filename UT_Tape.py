import unittest

# Module imports
from backend.Tape import E_LTO_Cap, E_LTOv, E_Tape, Tape

class UT_Tape(unittest.TestCase):

    AA: str    = "3810" # LTO3, Tape, no WP
    AB_WP: str = "8890" # LTO8, Tape, WP enabled
    AC_CS: str = "0810" # NONE, Tape, no WP

    def test_AA_sanity(self)-> None:
        "LTO3 Tape with no Write Protect"
        t: Tape = Tape(self.AA)

        try:
            self.assertEqual(t.lto_version, E_LTOv.LTO_3)
            self.assertEqual(t.native_capacity, E_LTO_Cap.LTO_3)
            self.assertEqual(t.write_protect, False)
            self.assertEqual(t.begin_of_tape, False)
            self.assertEqual(t.state, E_Tape.ONLINE)
            self.assertEqual(t.native_capacity.value, 300000000000) # type: ignore
            self.assertEqual(t.blocksize, "256K")

            self.assertIsInstance(t, Tape)
            self.assertIsInstance(t.lto_version, E_LTOv)
            self.assertIsInstance(t.native_capacity, E_LTO_Cap)
            self.assertIsInstance(t.state, E_Tape)

        except AssertionError:
            print(t)
            raise

        print(".A_TAPE")

    def test_AB_WriteProtect(self) -> None:
        "LTO8 Tape with Write Protect enabled, blocksize of 1GiB"
        t: Tape = Tape(self.AB_WP, "1G")

        try:
            self.assertEqual(t.lto_version, E_LTOv.LTO_8)
            self.assertEqual(t.native_capacity, E_LTO_Cap.LTO_8)
            self.assertEqual(t.write_protect, True)
            self.assertEqual(t.state, E_Tape.WRITE_PROTECT)
            self.assertEqual(t.native_capacity.value, 12000000000000) # type: ignore
            self.assertEqual(t.blocksize, "1G")

            self.assertIsInstance(t, Tape)
            self.assertIsInstance(t.lto_version, E_LTOv)
            self.assertIsInstance(t.native_capacity, E_LTO_Cap)
            self.assertIsInstance(t.state, E_Tape)

        except AssertionError:
            print(t)
            raise

        print("B_WRITEPROTECT")

    def test_AC_Custom(self) -> None:
        "Custom Tape with no WP and default Blocksize"
        t: Tape = Tape(self.AC_CS)
        t.native_capacity = 512

        try:
            self.assertEqual(t.lto_version, E_LTOv.NONE)
            self.assertEqual(t.native_capacity, 512)
            self.assertEqual(t.write_protect, False)
            self.assertEqual(t.state, E_Tape.ONLINE)
            self.assertEqual(t.blocksize, "256K")

            self.assertIsInstance(t, Tape)
            self.assertIsInstance(t.lto_version, E_LTOv)
            self.assertIsInstance(t.native_capacity, int)
            self.assertIsInstance(t.state, E_Tape)

        except AssertionError:
            print(t)
            raise

        print("C_CUSTOM")

if __name__ == '__main__':
    unittest.main()
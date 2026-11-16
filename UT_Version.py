import unittest

# Module imports
from backend.Version import Version

class UT_Version(unittest.TestCase):

    def test_AA_word(self) -> None:
        "4.0.0 is 0x4000 and survives the way through the 16 bit value"
        self.assertEqual(Version.text(), "4.0.0")
        self.assertEqual(Version.word(), 0x4000)
        self.assertEqual(Version.fromWord(Version.word()), Version.text())
        self.assertEqual(Version.fromWord(0x4A17), "4.10.23")
        print(".A_WORD")

if __name__ == '__main__':
    unittest.main()

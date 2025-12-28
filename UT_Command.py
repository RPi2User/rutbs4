import unittest
from time import sleep

# Module imports
from backend.Command import Command


class UT_Command(unittest.TestCase):

    def test_AA_create(self):
        c: Command = Command("")
        print("[CREATE] " + str(c))
        c.cleanup()

        self.assertTrue(True)

    def test_AB_validation(self):
        c: Command = Command("")

        self.assertEqual(c.cmd, "")
        self.assertEqual(c.pid, -1)
        self.assertEqual(c.running, False)
        self.assertEqual(c.stdout, [])
        self.assertEqual(c.stderr, [])
        self.assertEqual(c.filesize, -1)
        self.assertEqual(c.io, [])
        self.assertEqual(c.exitCode, -1)
        print("\n[VAL]")
        c.cleanup()

    def test_AC_start(self) -> None:
        c: Command = Command("cd")
        c.start()
        sleep(.1)
        str(c)  # trigger state refresh
        self.assertEqual(c.cmd, "cd")
        self.assertNotEqual(c.pid, 0)
        self.assertEqual(c.exitCode, 0)
        c.cleanup()


if __name__ == '__main__':
    unittest.main()
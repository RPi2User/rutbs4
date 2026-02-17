import unittest
from time import sleep, time

# Module imports
from backend.Job import Job
from backend.Command import Command


class UT_Command(unittest.TestCase):

    AA_CREATE: str = ""

    """_summary_
    """

    def test_AA_Add(self) -> None:
        """
        Job should be correctly initialized for appending stuff :3 
        """
        c: Command = Command(self.AA_CREATE)
        self.assertEqual(Job.Add(c), 0)
        print(".A_Add")

    def test_AB_Get()

if __name__ == '__main__':
    print("UT_Job:")
    unittest.main()
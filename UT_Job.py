import json
import unittest
from time import sleep, time

# Module imports
from backend.Job import Job, Entry
from backend.Command import Command


class UT_Command(unittest.TestCase):

    AA_ADD: str = "ping -c1 localhost"

    """_summary_
    """

    def test_AA_Add(self) -> None:
        """
        Job should be correctly initialized for appending stuff :3 
        """
        self.assertIsInstance(Job.DEFAULT_THREADLIMIT, int)
        self.assertIsInstance(Job.limit, int)
        self.assertGreater(Job.limit, 0)

        c: Command = Command(self.AA_ADD)

        self.assertEqual(Job.Add(c), 0)
        print(json.dumps(Job.Registry(), indent=2))
        print(".A_Add")

    def test_AB_Get(self) -> None:
        pass

if __name__ == '__main__':
    print("UT_Job:")
    unittest.main()
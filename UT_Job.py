import json
import unittest
from time import sleep, time

# Module imports
from backend.Job import Job, Entry
from backend.Command import Command


class UT_Command(unittest.TestCase):

    AA_ADD: str = "ping -c1 localhost"
    AB_DEP1_1D: str = "echo dependent"
    AB_DEP1_1F: str = "echo fulfillant"

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

        self.assertNotEqual(Job.Add(c), 0)
        self.assertNotEqual(Job.Add(c), 0)
        #self.assertNotEqual(Job.Add(c), 0)

        sleep(.1)

        print(json.dumps(Job.Registry(), indent=2))
        print(".A_Add")

    def test_AB_DEP1_1(self) -> None:
        return
        """
        This checks a 1:1 dependency tree.
        Process A can only be executed if B is done.
        """
        _dep: Command = Command(self.AB_DEP1_1D)
        _entry_dependant: str = Job.Add(_dep, True)
        _ful: Command = Command(self.AB_DEP1_1F)
        _entry_fulfillant: str = Job.Add(_ful, False, _entry_dependant)

        print(json.dumps(Job.Registry(), indent=2))
        print("B_DEP_1:1")

if __name__ == '__main__':
    print("UT_Job:")
    unittest.main()
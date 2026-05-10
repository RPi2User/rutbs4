import json
import unittest
from time import sleep, time

# Module imports
from backend.Job import Job, JobState, Entry, EntryState
from backend.Command import Command


class UT_Command(unittest.TestCase):

    AA_ADD: str = "ping -c1 localhost"
    AB_DEP1_1D: str = "echo need_ful"
    AB_DEP1_1F: str = "echo fulfillant"

    """_summary_
    Tests A:
        - tests the Core Structure

    Test B:
        - 
    """

    def test_AA_Add(self) -> None:
        """
        Job should be correctly initialized for appending stuff :3 
        """
        self.assertIsInstance(Job.DEFAULT_THREADLIMIT, int)
        self.assertIsInstance(Job.limit, int)
        self.assertGreater(Job.limit, 0)

        c: Command = Command(self.AA_ADD)
        
        p1: str = Job.Add(c)
        p2: str = Job.Add(c)

        self.assertNotEqual(p1, 0)
        self.assertNotEqual(p2, 0)
        self.assertNotEqual(p1, p2)

        try:
            Job.Get("---")
        except LookupError:
            self.assertTrue(True)

        self.assertEqual(len(Job.Registry()), 2)
        Job.Flush()
        self.assertEqual(len(Job.Registry()), 0)
        self.assertEqual(Job.state, JobState.EMPTY)

        print(".A_Add")

    def test_AB_DEP1_1(self) -> None:
        """
        This checks a 1:1 dependency tree.
        """

        _dep: Command = Command(self.AB_DEP1_1D)
        _proc: str = Job.Add(_dep, True)

        self.assertEqual(Job.Get(_proc).state, EntryState.ORPHAN)
        return

        _ful: Command = Command(self.AB_DEP1_1F)
        _entry_fulfillant: str = Job.Add(_ful, False, _entry_dependant)

        self.assertEqual(len(Job.queue), 2)
        self.assertNotEqual(_entry_dependant, _entry_fulfillant)

        self.assertEqual(Job.Get(_entry_dependant).dependsOn, _entry_fulfillant)

        self.assertEqual(Job.Get(_entry_dependant).state, EntryState.WAITING_FOR_PARENT) # IS STILL AN ORPHAN!
        self.assertEqual(Job.Get(_entry_fulfillant).state, EntryState.READY4EXEC)

        print("B_DEP_1:1")

if __name__ == '__main__':
    print("UT_Job:")
    unittest.main()
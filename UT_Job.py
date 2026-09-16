import os
import tempfile
import unittest
from time import sleep, time

# Module imports
from backend.Job import Job, JobState, Entry, EntryState
from backend.Command import Command


class UT_Job(unittest.TestCase):

    AA_ADD: str = "echo add"
    AB_DEP: str = "echo dep"
    AD_FAIL: str = "false"
    AE_SLEEP: str = "sleep 0.5"
    AG_WORK: str = "sleep 0.2"

    """_summary_
    Tests A:
        - AA-AB: Core structure (Add, Get, Registry, Flush, dependencies)
        - AC-AD: Dependency chains (order, failure propagation)
        - AE-AF: Scheduling (tape priority, one Entry per drive)
        - AG-AH: Flush(killRunning=False) and the JobScheduler thread

    Most tests call Job.Refresh() by hand, this keeps them deterministic.
    Depdencies:
    - sh, echo, sleep, false
    """

    def setUp(self) -> None:
        Job.Stop()
        Job.Flush()
        Job.limit = Job.DEFAULT_THREADLIMIT

    def tearDown(self) -> None:
        Job.Stop()
        Job.Flush()

    def _refreshUntilDone(self, timeoutSec: float = 5) -> None:
        end: float = time() + timeoutSec
        while any(e.state not in Job.FINISHED for e in Job.queue):
            if time() > end:
                self.fail("[FAIL] Timeout, queue did not finish: " + str(Job.Registry()))
            Job.Refresh()
            sleep(.01)

    def test_AA_Add(self) -> None:
        """
        Job should be correctly initialized for appending stuff :3
        """
        self.assertIsInstance(Job.DEFAULT_THREADLIMIT, int)
        self.assertGreater(Job.limit, 0)
        self.assertEqual(Job.state, JobState.EMPTY)

        c1: Command = Command(self.AA_ADD)
        p1: str = Job.Add(c1)
        p2: str = Job.Add(Command(self.AA_ADD))

        self.assertNotEqual(p1, "")
        self.assertNotEqual(p1, p2)
        self.assertEqual(Job.Get(p1).state, EntryState.READY4EXEC)
        self.assertEqual(Job.state, JobState.IDLE)

        with self.assertRaises(LookupError):
            Job.Get("---")
        with self.assertRaises(ValueError):   # the same Command object must not run twice
            Job.Add(c1)

        self.assertEqual(len(Job.Registry()), 2)
        Job.Flush()
        self.assertEqual(len(Job.Registry()), 0)
        self.assertEqual(Job.state, JobState.EMPTY)

        print(".A_ADD")

    def test_AB_DEP1_1(self) -> None:
        """
        This checks a 1:1 dependency: child waits for parent
        """
        parent: str = Job.Add(Command(self.AB_DEP))
        child: str = Job.Add(Command(self.AB_DEP), dependsOn=parent)

        self.assertEqual(Job.Get(child).dependsOn, parent)
        self.assertEqual(Job.Get(parent).state, EntryState.READY4EXEC)
        self.assertEqual(Job.Get(child).state, EntryState.WAITING_FOR_PARENT)

        with self.assertRaises(LookupError):  # parent must exist before the child
            Job.Add(Command(self.AB_DEP), dependsOn="---")

        self._refreshUntilDone()
        self.assertEqual(Job.Get(parent).state, EntryState.COMPLETED)
        self.assertEqual(Job.Get(child).state, EntryState.COMPLETED)
        print("B_DEP_1:1")

    def test_AC_Chain(self) -> None:
        """
        The 6 steps of a tape write must run strictly in order, even with many CPU slots
        """
        Job.limit = 8
        with tempfile.TemporaryDirectory() as tmp:
            log: str = os.path.join(tmp, "order.txt")
            last: str = ""
            for n in range(1, 7):
                last = Job.Add(Command(f"sh -c 'sleep 0.0{7 - n}; echo {n} >> {log}'"), dependsOn=last)

            self._refreshUntilDone()
            with open(log) as f:
                self.assertEqual(f.read().split(), ["1", "2", "3", "4", "5", "6"])

        print("C_CHAIN")

    def test_AD_Failed(self) -> None:
        """
        If a parent fails, the whole rest of the chain fails and never starts
        """
        a: str = Job.Add(Command(self.AD_FAIL))
        b: str = Job.Add(Command(self.AB_DEP), dependsOn=a)
        c: str = Job.Add(Command(self.AB_DEP), dependsOn=b)

        self._refreshUntilDone()
        self.assertEqual(Job.Get(a).state, EntryState.FAILED)
        self.assertEqual(Job.Get(b).state, EntryState.FAILED)
        self.assertEqual(Job.Get(c).state, EntryState.FAILED)
        self.assertFalse(Job.Get(b).command.didRun)
        self.assertFalse(Job.Get(c).command.didRun)
        print("D_FAILED")

    def test_AE_TapePriority(self) -> None:
        """
        With only one CPU slot, the Entry feeding the tape wins against older work
        """
        Job.limit = 1
        verify: str = Job.Add(Command(self.AE_SLEEP))               # no tape after this one
        encrypt: str = Job.Add(Command(self.AE_SLEEP))
        write: str = Job.Add(Command(self.AE_SLEEP), tape="/dev/nst0", dependsOn=encrypt)

        Job.Refresh()
        self.assertEqual(Job.Get(encrypt).state, EntryState.RUNNING)
        self.assertEqual(Job.Get(verify).state, EntryState.READY4EXEC)
        self.assertEqual(Job.Get(write).state, EntryState.WAITING_FOR_PARENT)
        self.assertEqual(Job.state, JobState.WORKING)

        self._refreshUntilDone()
        print("E_TAPE_PRIO")

    def test_AF_OnePerDrive(self) -> None:
        """
        Tape Entries ignore Job.limit, but only one Entry per drive may run
        """
        Job.limit = 1
        a: str = Job.Add(Command(self.AE_SLEEP), tape="/dev/nst0")
        b: str = Job.Add(Command(self.AE_SLEEP), tape="/dev/nst0")
        c: str = Job.Add(Command(self.AE_SLEEP), tape="/dev/nst1")
        d: str = Job.Add(Command(self.AE_SLEEP))

        Job.Refresh()
        self.assertEqual(Job.Get(a).state, EntryState.RUNNING)
        self.assertEqual(Job.Get(b).state, EntryState.READY4EXEC)
        self.assertEqual(Job.Get(c).state, EntryState.RUNNING)
        self.assertEqual(Job.Get(d).state, EntryState.RUNNING)

        self._refreshUntilDone()
        print("F_ONE_PER_DRIVE")

    def test_AG_FlushDone(self) -> None:
        """
        Flush(killRunning=False) removes only finished Entries
        """
        done: str = Job.Add(Command(self.AB_DEP))
        self._refreshUntilDone()

        running: str = Job.Add(Command(self.AE_SLEEP))
        waiting: str = Job.Add(Command(self.AB_DEP), dependsOn=running)
        Job.Refresh()

        Job.Flush(killRunning=False)
        self.assertEqual(set(Job.Registry()), {running, waiting})
        with self.assertRaises(LookupError):
            Job.Get(done)

        self._refreshUntilDone()
        Job.Flush(killRunning=False)
        self.assertEqual(Job.state, JobState.EMPTY)
        print("G_FLUSH_DONE")

    def test_AH_Work(self) -> None:
        """
        The JobScheduler thread finishes a chain on its own, Work() twice spawns one thread
        """
        last: str = ""
        for n in range(3):
            last = Job.Add(Command(self.AG_WORK), dependsOn=last)

        Job.Work(20)
        thread = Job.scheduler
        Job.Work(20)
        self.assertIs(Job.scheduler, thread)

        end: float = time() + 5
        while Job.Get(last).state is not EntryState.COMPLETED:
            self.assertLess(time(), end)
            sleep(.05)

        Job.Stop()
        self.assertIsNone(Job.scheduler)
        print("H_WORK")

if __name__ == '__main__':
    print("UT_Job:")
    unittest.main()
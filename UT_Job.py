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
        - AI-AJ: Tape order, abort of a runlist
        - AR: Entry.drive, Registry(drive=), Flush(drive=)
        - AM-AP: Urgent Entries (system commands): own list, no slot, deadline, from a prepare hook

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

    def test_AB_WAITFOR(self) -> None:
        """
        A barrier: the child starts when ALL of its parents are COMPLETED, and fails if one of them fails
        """
        a: str = Job.Add(Command("sleep 0.3"))
        b: str = Job.Add(Command(self.AB_DEP))
        barrier: str = Job.Add(Command(self.AB_DEP), waitFor=[a, b])
        self.assertEqual(Job.Get(barrier).state, EntryState.WAITING_FOR_PARENT)
        with self.assertRaises(LookupError):
            Job.Add(Command(self.AB_DEP), waitFor=[a, "---"])

        self._refreshUntilDone()
        self.assertEqual(Job.Get(barrier).state, EntryState.COMPLETED)

        bad: str = Job.Add(Command("false"))
        good: str = Job.Add(Command(self.AB_DEP))
        child: str = Job.Add(Command(self.AB_DEP), dependsOn=good, waitFor=[bad])
        self._refreshUntilDone()
        self.assertEqual(Job.Get(good).state, EntryState.COMPLETED)
        self.assertEqual(Job.Get(child).state, EntryState.FAILED)

        # A closing step waits for its waitFor to END, good or bad, and then runs
        slow: str = Job.Add(Command("sleep 0.3"))
        closing: str = Job.Add(Command(self.AB_DEP), waitFor=[bad, slow], always=True)
        self.assertEqual(Job.Get(closing).state, EntryState.WAITING_FOR_PARENT)     # slow is not finished
        self._refreshUntilDone()
        self.assertEqual(Job.Get(closing).state, EntryState.COMPLETED)
        # its dependsOn still has to be good
        self.assertEqual(Job.Get(Job.Add(Command(self.AB_DEP), dependsOn=bad, waitFor=[good], always=True)).state, EntryState.FAILED)
        print("B_WAITFOR")

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

    def test_AI_TapeOrder(self) -> None:
        """
        A drive writes in the order of Job.Add(), even if a later Entry is ready first
        """
        with tempfile.TemporaryDirectory() as tmp:
            log: str = os.path.join(tmp, "order.txt")
            slow: str = Job.Add(Command("sleep 0.3"))
            Job.Add(Command(f"sh -c 'echo 1 >> {log}'"), tape="/dev/nst0", dependsOn=slow)
            fast: str = Job.Add(Command("sleep 0.05"))
            Job.Add(Command(f"sh -c 'echo 2 >> {log}'"), tape="/dev/nst0", dependsOn=fast)

            self._refreshUntilDone()
            with open(log) as f:
                self.assertEqual(f.read().split(), ["1", "2"])

        print("I_TAPE_ORDER")

    def test_AJ_Runlist(self) -> None:
        """
        One failure aborts its runlist, closing steps still run, other runlists are untouched
        """
        Job.limit = 1   # one after the other, in the order of Add()
        first: str = Job.Add(Command(self.AB_DEP), runlist="r1")
        bad: str = Job.Add(Command(self.AD_FAIL), runlist="r1")
        later: str = Job.Add(Command(self.AB_DEP), runlist="r1")
        closing: str = Job.Add(Command(self.AB_DEP), runlist="r1", always=True)
        other: str = Job.Add(Command(self.AB_DEP), runlist="r2")

        self._refreshUntilDone()
        self.assertEqual(Job.Get(first).state, EntryState.COMPLETED)
        self.assertEqual(Job.Get(bad).state, EntryState.FAILED)
        self.assertEqual(Job.Get(later).state, EntryState.FAILED)
        self.assertFalse(Job.Get(later).command.didRun)
        self.assertEqual(Job.Get(closing).state, EntryState.COMPLETED)
        self.assertEqual(Job.Get(other).state, EntryState.COMPLETED)
        print("J_RUNLIST")

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

    def test_AK_prepare(self) -> None:
        """
        prepare() runs right before the Command starts, never before the parent is done.
        A prepare that raises fails the Entry, the Command never ran.
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker: str = os.path.join(tmp, "marker")

            def make() -> None:
                with open(marker, "w") as f:
                    f.write("prepared")

            first: str = Job.Add(Command("sleep 0.2"))
            second: str = Job.Add(Command("cat " + Command.quote(marker)), dependsOn=first, prepare=make)
            Job.Refresh()
            self.assertFalse(os.path.exists(marker))        # the parent is still running

            self._refreshUntilDone()
            self.assertEqual(Job.Get(second).state, EntryState.COMPLETED)
            self.assertEqual(Job.Get(second).command.stdout, ["prepared"])

            def broken() -> None:
                raise OSError("no space left")

            failing: Command = Command("echo never")
            e: str = Job.Add(failing, prepare=broken)
            self._refreshUntilDone()
            self.assertEqual(Job.Get(e).state, EntryState.FAILED)
            self.assertIn("no space left", Job.Get(e).error)
            self.assertFalse(failing.didRun)
        print("K_PREPARE")

    def test_AL_failed(self) -> None:
        """
        Job.Failed(runlist): a failed Entry of the runlist counts, a failed closing step and other runlists do not
        """
        Job.Add(Command(self.AD_FAIL), runlist="a")
        Job.Add(Command(self.AB_DEP), runlist="b")
        self._refreshUntilDone()
        self.assertTrue(Job.Failed("a"))
        self.assertFalse(Job.Failed("b"))

        Job.Flush()
        Job.Add(Command(self.AB_DEP), runlist="c")
        Job.Add(Command(self.AD_FAIL), runlist="c", always=True)
        self._refreshUntilDone()
        self.assertFalse(Job.Failed("c"))
        print("L_FAILED")

    def test_AM_urgent(self) -> None:
        """Add(urgent=True) starts at once, stands alone and lives outside the queue"""
        c: Command = Command(self.AB_DEP)
        e: str = Job.Add(c, urgent=True)
        self.assertTrue(c.didRun)                       # started by the Entry constructor, no Refresh needed
        self.assertEqual(Job.Get(e).urgent, True)
        self.assertEqual(Job.queue, [])
        self.assertEqual(Job.state, JobState.EMPTY)
        self.assertTrue(Job.Wait([e], 5))
        self.assertEqual(Job.Get(e).state, EntryState.COMPLETED)
        self.assertIn(e, Job.Registry())
        self.assertTrue(Job.Registry()[e]["Entry"]["urgent"])

        with self.assertRaises(ValueError):             # same object twice
            Job.Add(c, urgent=True)
        for bad in [{"tape": "/dev/nst0"}, {"dependsOn": e}, {"runlist": "r"}, {"always": True}, {"waitFor": [e]}]:
            with self.assertRaises(ValueError):
                Job.Add(Command(self.AB_DEP), urgent=True, **bad)
        print("M_URGENT")

    def test_AN_urgent_no_slot(self) -> None:
        """An urgent Entry does not wait for the thread limit and does not take a slot"""
        Job.limit = 1
        busy: str = Job.Add(Command("sleep 0.5"))
        Job.Refresh()
        self.assertEqual(Job.Get(busy).state, EntryState.RUNNING)

        beg: float = time()
        c: Command = Job.Run(Command(self.AB_DEP))
        self.assertLess(time() - beg, 0.4)
        self.assertEqual(c.stdout, ["dep"])
        self.assertEqual(Job.Get(busy).state, EntryState.RUNNING)   # the slot was not touched

        waiting: str = Job.Add(Command(self.AB_DEP))
        Job.Refresh()
        self.assertEqual(Job.Get(waiting).state, EntryState.READY4EXEC)    # still no slot for queued work
        print("N_URGENT_NO_SLOT")

    def test_AO_deadline(self) -> None:
        """A late urgent Entry is KILLED (not FAILED), by Run, by Get and by Refresh"""
        c: Command = Job.Run(Command("ping localhost -c 10"), deadlineMs=300)
        self.assertTrue(c.killed)
        self.assertFalse(c.running)

        e: str = Job.Add(Command("ping localhost -c 10"), urgent=True, deadlineMs=200)
        self.assertEqual(Job.Get(e).state, EntryState.RUNNING)
        sleep(.3)
        Job.Refresh()                                   # the scheduler thread does this every tick
        self.assertEqual(Job.Get(e).state, EntryState.KILLED)
        self.assertIn(EntryState.KILLED, Job.FINISHED)

        child: str = Job.Add(Command(self.AB_DEP), dependsOn=e)     # a KILLED parent fails the child
        self.assertEqual(Job.Get(child).state, EntryState.FAILED)
        print("O_DEADLINE")

    def test_AP_urgent_in_prepare(self) -> None:
        """Constructors and prepare hooks run under the Job lock: Run() there must not disturb the queue"""
        seen: list = []

        def hook() -> None:
            seen.append(Job.Run(Command("echo from-hook")).stdout[0])

        e: str = Job.Add(Command(self.AB_DEP), prepare=hook)
        after: str = Job.Add(Command(self.AB_DEP), dependsOn=e)
        self._refreshUntilDone()
        self.assertEqual(seen, ["from-hook"])
        self.assertEqual((Job.Get(e).state, Job.Get(after).state), (EntryState.COMPLETED, EntryState.COMPLETED))
        print("P_URGENT_IN_PREPARE")

    def test_AQ_registry_limit(self) -> None:
        """The registry of system commands keeps only the last URGENT_KEEP finished ones; Flush empties it"""
        keep: int = Job.URGENT_KEEP
        Job.URGENT_KEEP = 5
        try:
            for n in range(8):
                Job.Run(Command("echo " + str(n)))
            self.assertLessEqual(len(Job.urgent), 6)
            self.assertEqual(Job.urgent[-1].command.stdout, ["7"])
        finally:
            Job.URGENT_KEEP = keep
        Job.Flush()
        self.assertEqual(Job.urgent, [])
        print("Q_REGISTRY_LIMIT")


    def test_AR_drive(self) -> None:
        """Entry.drive: a tape Entry belongs to its drive, others get it from the request; Registry and Flush can filter"""
        a1: str = Job.Add(Command(self.AB_DEP), drive="wwid-A")
        a2: str = Job.Add(Command("sleep 0.5"), tape="wwid-A", dependsOn=a1)        # drive follows from tape
        b1: str = Job.Add(Command("sleep 0.5"), tape="wwid-B")
        b2: str = Job.Add(Command(self.AB_DEP), drive="wwid-B", dependsOn=b1)
        free: str = Job.Add(Command(self.AB_DEP))                                   # no drive at all
        sys_a: str = Job.Add(Command(self.AB_DEP), urgent=True, drive="wwid-A")     # a SCSI query of drive A
        self.assertEqual([Job.Get(i).drive for i in (a1, a2, b1, b2, free, sys_a)],
                         ["wwid-A", "wwid-A", "wwid-B", "wwid-B", "", "wwid-A"])
        self.assertEqual(Job.Registry(drive="wwid-A").keys(), {a1, a2, sys_a})
        self.assertEqual(Job.Registry(drive="wwid-B").keys(), {b1, b2})
        self.assertEqual(Job.Registry()[a2]["Entry"]["drive"], "wwid-A")
        self.assertEqual(Job.Registry(drive="nobody"), {})

        self.assertTrue(Job.Wait([a1, sys_a], 5))
        Job.Refresh()
        self.assertEqual(Job.Get(a2).state, EntryState.RUNNING)
        self.assertEqual(Job.Get(b1).state, EntryState.RUNNING)

        # the next request of drive A replaces what is left of A, drive B is not touched, not even killed
        Job.Flush(killRunning=False, drive="wwid-A")
        self.assertEqual(Job.Registry().keys(), {a2, b1, b2, free})                 # only the finished ones of A are gone
        Job.Flush(killRunning=True, drive="wwid-A")
        self.assertEqual(Job.Registry().keys(), {b1, b2, free})
        self.assertEqual(Job.Get(b1).state, EntryState.RUNNING)                     # still running
        Job.Flush(killRunning=True)
        self.assertEqual(Job.Registry(), {})
        print("R_DRIVE")


if __name__ == '__main__':
    print("UT_Job:")
    unittest.main()
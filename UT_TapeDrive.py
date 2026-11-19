import os
import tempfile
import unittest

# Module imports
from backend.Command import Command
from backend.Job import Job
from backend.Tape import Tape, E_Tape
from backend.TapeDrive import TapeDrive, TD_State


class UT_TapeDrive(unittest.TestCase):

    """_summary_
    A tape drive does four things (and seeks), each one a step in the Job queue.
    Tests A:
        - A: the commands of the four steps (real drive: SCSI via sg_raw, dd on the nst device)
        - B: state and tape position are derived from the Job entries
        - C: an override is a template, every step gets its own Command
        - D: the last finished step failed -> ERROR, the next good one clears it
    Depdencies:
    - none (no SCSI command is sent: drive_override)
    """

    def setUp(self) -> None:
        Job.Stop()
        Job.Flush()

    def tearDown(self) -> None:
        Job.Flush()

    def _drive(self, tmp: str) -> TapeDrive:
        td: TapeDrive = TapeDrive(os.path.join(tmp, "fake.bin"), "/dev/sg99", drive_override=True)
        open(td.path, "wb").close()
        td.tapeOverride(Tape("8800"))
        return td

    def test_A_commands(self) -> None:
        td: TapeDrive = TapeDrive("/dev/nst0", "/dev/sg12", drive_override=True, blocksize="384K")
        td.Rewind(); td.Eject(); td.Write("/in/some file", 11); td.Read("/out/x", 11)
        td.Read("/out/toc", count=4096); td.Space(1); td.Space(-2); td.SpaceEnd()
        commands: list = [Job.Get(e).command.cmd for _, e in td.entries]

        self.assertEqual(commands[0], "sg_raw '/dev/sg12' 0x01 0 0 0 0 0")
        self.assertEqual(commands[1], "sg_raw '/dev/sg12' 0x1B 0 0 0 0 0")
        self.assertEqual(commands[2], "dd if='/in/some file' of='/dev/nst0' iflag=fullblock status=none bs=384K")
        self.assertEqual(commands[3], "dd if='/dev/nst0' of='/out/x' status=none bs=8M")                # no fullblock, see TapeDrive
        self.assertEqual(commands[4], "dd if='/dev/nst0' of='/out/toc' status=none bs=8M count=4096")
        self.assertEqual(commands[5], "sg_raw '/dev/sg12' 0x11 0x01 0x00 0x00 0x01 0")                  # forward 1 file mark
        self.assertEqual(commands[6], "sg_raw '/dev/sg12' 0x11 0x01 0xff 0xff 0xfe 0")                  # back 2 (24 bit, two's complement)
        self.assertEqual(commands[7], "sg_raw '/dev/sg12' 0x11 0x03 0 0 0 0")                           # to the end of the data
        self.assertTrue(all(Job.Get(e).tape == td.id for _, e in td.entries))      # one at a time per drive
        self.assertFalse(any("mt " in c for c in commands))                         # SCSI only
        with self.assertRaises(ValueError):
            td.Space(0x800000)
        Job.Flush()      # nothing was started, the drive is a fake
        print(".A_COMMANDS")

    def test_B_stateIsDerived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            td.rewindCommand = Command("true")
            src: str = os.path.join(tmp, "src")
            with open(src, "w") as f:
                f.write("data")

            self.assertEqual(td.state, TD_State.IDLE)
            rewind: str = td.Rewind()
            write: str = td.Write(src, dependsOn=rewind)
            self.assertEqual(td.state, TD_State.QUEUED)

            self.assertTrue(Job.Wait([write], 10))
            self.assertEqual(td.state, TD_State.IDLE)
            self.assertFalse(td.tape.begin_of_tape)             # the last step was a write

            self.assertTrue(Job.Wait([td.Rewind()], 10))
            self.assertEqual(td.state, TD_State.IDLE)
            self.assertTrue(td.tape.begin_of_tape)
            self.assertEqual(td.tape.state, E_Tape.ONLINE)
        print("B_STATE_DERIVED")

    def test_C_overrideIsATemplate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            td.rewindCommand = Command("true")
            first: str = td.Rewind()
            second: str = td.Rewind()       # the same override again, in the same queue
            self.assertIsNot(Job.Get(first).command, Job.Get(second).command)
            self.assertTrue(Job.Wait([first, second], 10))
        print("C_TEMPLATE")

    def test_D_errorUntilNextGoodStep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            self.assertTrue(Job.Wait([td.Write(os.path.join(tmp, "does-not-exist"))], 10))
            self.assertEqual(td.state, TD_State.ERROR)

            td.rewindCommand = Command("true")
            self.assertTrue(Job.Wait([td.Rewind()], 10))
            self.assertEqual(td.state, TD_State.IDLE)
        print("D_ERROR_CLEARED")

    def test_E_asdictIsJson(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            self.assertEqual(json.loads(str(td))["state"], "IDLE")
            self.assertIn("\n  ", str(td))        # indent=2
        print("E_STR")


if __name__ == "__main__":
    unittest.main()

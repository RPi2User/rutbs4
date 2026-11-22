import os
import subprocess
import sys
import tempfile
import unittest

# Module imports
from backend import TapeIoctl
from backend.Command import Command
from backend.Job import Job
from backend.Tape import Tape, E_Tape
from backend.TapeDrive import TapeDrive, TD_State


class UT_TapeDrive(unittest.TestCase):

    """_summary_
    A tape drive does four things (and seeks), each one a step in the Job queue.
    Tests A:
        - A: the commands of the steps (real drive: the st driver via TapeIoctl, dd on the nst device)
        - B: state and tape position are derived from the Job entries
        - C: an override is a template, every step gets its own Command
        - D: the last finished step failed -> ERROR, the next good one clears it
        - F: block sizes: what may be one, and the minimum for a read
        - G: the answers of a rewind: no tape, busy, anything else; the next good rewind says ONLINE
        - H: the rewind helper: exit codes, a file is not a tape
        - I: a drive that does not tell what is in it is UNKNOWN and works
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
        td.tapeOverride(Tape("8800", td.generic_path))
        return td

    def test_A_commands(self) -> None:
        td: TapeDrive = TapeDrive("/dev/nst0", "/dev/sg12", drive_override=True, blocksize="384K")
        td.Rewind(); td.Eject(); td.Write("/in/some file", 11); td.Read("/out/x", 11)
        td.Read("/out/toc", count=4096); td.Space(1); td.Space(-2); td.SpaceEnd()
        commands: list = [Job.Get(e).command.cmd for _, e in td.entries]

        ioctl: str = "'" + sys.executable + "' '" + TapeIoctl.__file__ + "' "
        self.assertEqual(commands[0], ioctl + "rewind '/dev/nst0'")
        self.assertEqual(commands[1], ioctl + "eject '/dev/nst0'")
        self.assertEqual(commands[2], "dd if='/in/some file' of='/dev/nst0' iflag=fullblock status=none bs=384K")
        self.assertEqual(commands[3], "dd if='/dev/nst0' of='/out/x' status=none bs=256K")                # no fullblock, see TapeDrive
        self.assertEqual(commands[4], "dd if='/dev/nst0' of='/out/toc' status=none bs=256K count=4096")
        self.assertEqual(commands[5], "sg_raw -t 900 '/dev/sg12' 0x11 0x01 0x00 0x00 0x01 0")                  # forward 1 file mark
        self.assertEqual(commands[6], "sg_raw -t 900 '/dev/sg12' 0x11 0x01 0xff 0xff 0xfe 0")                  # back 2 (24 bit, two's complement)
        self.assertEqual(commands[7], "sg_raw -t 900 '/dev/sg12' 0x11 0x03 0 0 0 0")                           # to the end of the data
        self.assertTrue(all(Job.Get(e).tape == td.id for _, e in td.entries))      # one at a time per drive
        self.assertFalse(any(c.startswith("mt ") for c in commands))
        self.assertTrue(all(Job.Get(e).command.env == {"LC_ALL": "C"} for _, e in td.entries[2:5]))     # dd speaks English
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

    def test_F_blocksizes(self) -> None:
        self.assertEqual([TapeDrive.blockBytes(b) for b in ("512", "256K", "1M")], [512, 256 * 1024, 1 << 20])
        for bad in ("", "0", "1G", "1K; reboot", "-1", "1 K", "$(x)", "1K\n"):
            with self.assertRaises(ValueError, msg=bad):
                TapeDrive.blockBytes(bad)
        self.assertEqual([TapeDrive.readBlock(b) for b in ("", "128K", "256K", "1M")], ["256K", "256K", "256K", "1M"])

        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            td.Write("/x", blocksize="256K"); td.Read("/y", blocksize="4M")
            commands: list = [Job.Get(e).command.cmd for _, e in td.entries]
            self.assertIn("bs=256K", commands[0])
            self.assertIn("bs=4M", commands[1])
        print("F_BLOCKSIZES")

    def test_G_rewindAnswers(self) -> None:
        for code, state in ((TapeIoctl.NO_MEDIUM, TD_State.NO_TAPE), (TapeIoctl.BUSY, TD_State.BUSY), (1, TD_State.ERROR)):
            with tempfile.TemporaryDirectory() as tmp:
                td: TapeDrive = self._drive(tmp)
                td.rewindCommand = Command("sh -c 'exit " + str(code) + "'")
                self.assertTrue(Job.Wait([td.Rewind()], 10))
                self.assertEqual(td.state, state)
                self.assertEqual(td.tape.state, E_Tape.NO_TAPE if state is TD_State.NO_TAPE else E_Tape.ONLINE)

                td.rewindCommand = Command("true")                          # a tape was inserted, or the other one is done
                self.assertTrue(Job.Wait([td.Rewind()], 10))
                self.assertEqual((td.state, td.tape.state), (TD_State.IDLE, E_Tape.ONLINE))
        # a dd that happens to end with the same number is an ordinary error
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(TapeDrive._failure(TD_State.WRITE, TapeIoctl.BUSY), TD_State.ERROR)
        print("G_REWIND_ANSWERS")

    def test_H_ioctlHelper(self) -> None:
        import errno
        self.assertEqual([TapeIoctl.exitCode(n) for n in (errno.ENOMEDIUM, errno.EBUSY, errno.EIO)], [10, 11, 1])
        with tempfile.TemporaryDirectory() as tmp:
            plain: str = os.path.join(tmp, "not a tape")
            open(plain, "wb").close()
            for args, code in ((["rewind", plain], 1), (["rewind", plain + "x"], 1), (["format", plain], 2), ([], 2)):
                done = subprocess.run([sys.executable, TapeIoctl.__file__] + args, capture_output=True, text=True)
                self.assertEqual(done.returncode, code, done.stderr)
                self.assertTrue(done.stderr)
        print("H_IOCTL_HELPER")

    def test_I_unknownTape(self) -> None:
        td: TapeDrive = TapeDrive("/dev/null", "")          # no sg device: nobody to ask
        self.assertEqual((td.tape.state, td.error, td.state), (E_Tape.UNKNOWN, "", TD_State.IDLE))
        self.assertFalse(td.tape.write_protect)

        TapeDrive.inquiryCommand = Command("false")         # the drive does not answer the INQUIRY
        try:
            td = TapeDrive("/dev/null", "/dev/null")
        finally:
            TapeDrive.inquiryCommand = None                 # type: ignore
        self.assertIn("INQUIRY failed", td.error)
        self.assertEqual((td.tape.state, td.state), (E_Tape.UNKNOWN, TD_State.IDLE))
        print("I_UNKNOWN_TAPE")

    def test_E_asdictIsJson(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            self.assertEqual(json.loads(str(td))["state"], "IDLE")
            self.assertIn("\n  ", str(td))        # indent=2
        print("E_STR")


if __name__ == "__main__":
    unittest.main()

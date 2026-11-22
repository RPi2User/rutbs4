import contextlib
import io
import os
import struct
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
        - I: what is in the drive (MTIOCGET); a drive that does not tell is UNKNOWN and works
        - J: a drive that hangs or is busy
        - K: what goes into the ioctls
    Depdencies:
    - none (no drive is asked: drive_override, fake ioctls)
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
        td.Read("/out/toc", count=4096)
        commands: list = [Job.Get(e).command.cmd for _, e in td.entries]

        ioctl: str = "'" + sys.executable + "' '" + TapeIoctl.__file__ + "' "
        self.assertEqual(commands[0], ioctl + "rewind '/dev/nst0'")
        self.assertEqual(commands[1], ioctl + "eject '/dev/nst0'")
        self.assertEqual(commands[2], "dd if='/in/some file' of='/dev/nst0' iflag=fullblock status=none bs=384K")
        self.assertEqual(commands[3], "dd if='/dev/nst0' of='/out/x' status=none bs=256K")                # no fullblock, see TapeDrive
        self.assertEqual(commands[4], "dd if='/dev/nst0' of='/out/toc' status=none bs=256K count=4096")
        self.assertTrue(all(Job.Get(e).tape == td.id for _, e in td.entries))      # one at a time per drive
        self.assertFalse(any(c.startswith("mt ") for c in commands))
        self.assertTrue(all(Job.Get(e).command.env == {"LC_ALL": "C"} for _, e in td.entries[2:5]))     # dd speaks English
        self.assertFalse(any("sg_" in c or "/dev/sg" in c for c in commands))
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
            self.assertEqual((td.blocksize, td.tocBlock()), ("128K", "128K"))
            td.blocksize = "1M"; self.assertEqual(td.tocBlock(), "128K")
            td.blocksize = "64K"; self.assertEqual(td.tocBlock(), "64K")        # the drive takes nothing bigger
            td.Write("/x", blocksize="256K"); td.Read("/y", blocksize="4M")
            commands: list = [Job.Get(e).command.cmd for _, e in td.entries]
            self.assertIn("bs=256K", commands[0])
            self.assertIn("bs=4M", commands[1])
        print("F_BLOCKSIZES")

    def test_G_rewindAnswers(self) -> None:
        for code, state in ((TapeIoctl.NO_MEDIUM, TD_State.NO_TAPE), (TapeIoctl.BUSY, TD_State.BUSY), (TapeIoctl.NOT_READY, TD_State.NOT_READY), (1, TD_State.ERROR)):
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

            # a rewind also switches to variable block mode, after the rewind; an eject does not
            real = TapeIoctl.fcntl.ioctl
            calls: list = []
            try:
                TapeIoctl.fcntl.ioctl = lambda fd, request, data: calls.append((request, data))      # type: ignore
                TapeIoctl.operate("rewind", plain)
                TapeIoctl.operate("eject", plain)
                self.assertEqual(calls, [(TapeIoctl.MTIOCTOP, struct.pack("hi", op, count)) for op, count in ((6, 1), (20, 0), (7, 1))])

                def refusing(fd, request, data):        # the drive takes the rewind but not the mode
                    if struct.unpack("hi", data)[0] == TapeIoctl.MTSETBLK:
                        raise OSError(errno.EIO, "refused")
                TapeIoctl.fcntl.ioctl = refusing        # type: ignore
                with self.assertRaises(OSError):
                    TapeIoctl.operate("rewind", plain)

                # EIO of a rewind: loading or unloading (neither ready nor empty), or an ordinary error
                realStatus = TapeIoctl.status
                for online, noTape, code in ((False, False, TapeIoctl.NOT_READY), (True, False, 1), (False, True, 1)):
                    TapeIoctl.status = lambda device: {"online": online, "noTape": noTape}      # type: ignore
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(TapeIoctl.main(["rewind", plain]), code)
                TapeIoctl.status = realStatus
            finally:
                TapeIoctl.fcntl.ioctl = real
        print("H_IOCTL_HELPER")

    def test_I_whatIsInTheDrive(self) -> None:
        "The answers of MTIOCGET, and that no answer is no reason to refuse anything"
        def drive(**answer) -> TapeDrive:
            base: dict = {"noTape": False, "writeProtect": False, "beginOfTape": True, "online": True, "density": 0x44, "blocksize": 0}
            real = (TapeIoctl.status, TapeIoctl.serial)
            try:
                TapeIoctl.status = lambda device: {**base, **answer}       # type: ignore
                TapeIoctl.serial = lambda device: "1210173183"              # type: ignore
                return TapeDrive("/dev/null", "")
            finally:
                TapeIoctl.status, TapeIoctl.serial = real                   # type: ignore

        td: TapeDrive = drive()
        self.assertEqual((td.tape.state, td.tape.lto_version.name, td.tape.write_protect, td.tape.begin_of_tape, td.serial),
                         (E_Tape.ONLINE, "LTO_3", False, True, "1210173183"))
        self.assertEqual((td.tape.native_capacity, td.tape.cartridgeMemory.device), (300 * 10**9, "/dev/null"))
        self.assertEqual((drive(writeProtect=True).tape.state, drive(writeProtect=True).tape.write_protect), (E_Tape.WRITE_PROTECT, True))
        self.assertEqual(drive(noTape=True, online=False).tape.state, E_Tape.NO_TAPE)
        # neither ready nor empty, as measured for 6 s after an eject and for 10 s while a tape is loaded
        loading: TapeDrive = drive(online=False, density=0, beginOfTape=False)
        self.assertEqual(loading.tape.state, E_Tape.NOT_READY)
        loading.refreshTape = lambda: None                                  # type: ignore
        with self.assertRaisesRegex(ValueError, "loading or unloading"):
            loading.requireTape()
        for density, version in ((0x40, "LTO_1"), (0x46, "LTO_4"), (0x58, "LTO_5"), (0x5E, "LTO_8"), (0x60, "LTO_9")):
            self.assertEqual(drive(density=density).tape.lto_version.name, version)
        unknown: TapeDrive = drive(density=0x99)                            # a tape, but nobody knows which
        self.assertEqual((unknown.tape.state, unknown.tape.lto_version.name, unknown.tape.native_capacity), (E_Tape.ONLINE, "NONE", 0))

        td = TapeDrive("/dev/null", "")                                     # not a tape drive at all: no answer
        self.assertEqual((td.tape.state, td.serial, td.state), (E_Tape.UNKNOWN, "", TD_State.IDLE))
        self.assertTrue(td.error)
        self.assertFalse(td.tape.write_protect)
        print("I_WHAT_IS_IN_THE_DRIVE")

    def test_J_hungDrive(self) -> None:
        "A drive that does not answer does not hang us, and one that is busy keeps what is known"
        import threading, time
        release = threading.Event()
        real = (TapeIoctl.status, TapeIoctl.serial, TapeDrive.ASK_TIMEOUT)
        try:
            TapeDrive.ASK_TIMEOUT = 0.1
            TapeIoctl.serial = lambda device: ""                            # type: ignore
            TapeIoctl.status = lambda device: release.wait(5)               # type: ignore
            start: float = time.monotonic()
            td: TapeDrive = TapeDrive("/dev/null", "")
            self.assertLess(time.monotonic() - start, 1)
            self.assertEqual(td.tape.state, E_Tape.UNKNOWN)
            self.assertIn("no answer", td.error)

            TapeIoctl.status = lambda device: {"noTape": False, "writeProtect": False, "beginOfTape": True, "online": True, "density": 0x5E, "blocksize": 0}   # type: ignore
            td.refreshTape()
            def busy(device):
                raise OSError(16, "Device or resource busy")
            TapeIoctl.status = busy                                         # type: ignore
            td.refreshTape()
            self.assertEqual((td.tape.state, td.tape.lto_version.name), (E_Tape.ONLINE, "LTO_8"))
        finally:
            release.set()
            TapeIoctl.status, TapeIoctl.serial, TapeDrive.ASK_TIMEOUT = real   # type: ignore
        print("J_HUNG_DRIVE")

    def test_K_ioctlData(self) -> None:
        "What goes into the ioctls: the layout of struct mtget and sg_io_hdr, the commands of the cartridge memory"
        import ctypes
        self.assertEqual(ctypes.sizeof(TapeIoctl.SG_Header), 88 if ctypes.sizeof(ctypes.c_void_p) == 8 else 64)
        data: bytes = TapeIoctl.attributeData(["rutbs", "4000", "fingerprint"])
        self.assertEqual(len(data), 4 + 3 * 5 + 32 + 8 + 160)
        self.assertEqual(data[:4], struct.pack(">I", len(data) - 4))
        self.assertEqual(data[4:9], bytes([0x08, 0x01, 1, 0, 32]))
        self.assertEqual(data[9:41], b"rutbs".ljust(32))
        self.assertTrue(data.endswith(b"fingerprint".ljust(160, b"\0")))
        with self.assertRaises(ValueError):
            TapeIoctl.attributeData(["x" * 33, "4000", "f"])

        calls: list = []
        real = TapeIoctl.fcntl.ioctl
        def fake(fd, request, argument):
            self.assertEqual(request, TapeIoctl.SG_IO)
            cdb: bytes = ctypes.string_at(argument.cmdp, argument.cmd_len)
            out: bytes = ctypes.string_at(argument.dxferp, argument.dxfer_len) if argument.dxfer_direction == TapeIoctl.DXFER_TO_DEV else b""
            calls.append((cdb.hex(), argument.dxfer_direction, argument.dxfer_len, out[:4].hex()))
            if argument.dxfer_direction == TapeIoctl.DXFER_FROM_DEV:
                answer: bytes = (bytes([1, 0x80, 0, 10]) + b"1210173183") if cdb[0] == 0x12 else struct.pack(">I", 0)
                ctypes.memmove(argument.dxferp, answer, len(answer)); argument.resid = argument.dxfer_len - len(answer)
        with tempfile.TemporaryDirectory() as tmp:
            plain: str = os.path.join(tmp, "x"); open(plain, "wb").close()
            TapeIoctl.fcntl.ioctl = fake                                    # type: ignore
            try:
                self.assertEqual(TapeIoctl.serial(plain), "1210173183")
                self.assertEqual(TapeIoctl.readAttributes(plain), struct.pack(">I", 0))
                TapeIoctl.writeAttributes(plain, ["rutbs", "4000", "fp"])
                def refused(fd, request, argument):
                    argument.host_status = 5
                TapeIoctl.fcntl.ioctl = refused                             # type: ignore
                with self.assertRaisesRegex(OSError, "host 0x05"):
                    TapeIoctl.readAttributes(plain)
            finally:
                TapeIoctl.fcntl.ioctl = real                                # type: ignore
        self.assertEqual(calls[0], ("12018000fc00", TapeIoctl.DXFER_FROM_DEV, 252, ""))
        self.assertEqual(calls[1], ("8c000000000000000000000020000000", TapeIoctl.DXFER_FROM_DEV, 8192, ""))
        self.assertEqual(calls[2][0], "8d000000000000000000%08x0000" % len(data))
        self.assertEqual(calls[2][1:3], (TapeIoctl.DXFER_TO_DEV, len(data)))
        print("K_IOCTL_DATA")

    def test_E_asdictIsJson(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            self.assertEqual(json.loads(str(td))["state"], "IDLE")
            self.assertIn("\n  ", str(td))        # indent=2
        print("E_STR")


if __name__ == "__main__":
    unittest.main()

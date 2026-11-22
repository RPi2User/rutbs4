import json
import os
import re
import sys
import threading
from typing import List, Tuple
from enum import Enum

from backend.Command import Command
from backend.Job import EntryState, Job

from backend import TapeIoctl
from backend.CartridgeMemory import CartridgeMemory
from backend.Tape import Tape, E_Tape

"""_summary_

    How we talk to a tape drive:

    The OS only has to give: the list of the nst devices, rewind, eject, `dd if=` and `dd of=`. Rewind and eject are ioctls on the
    nst device (see TapeIoctl). There is no `mt`, no sg3_utils and no /dev/sgX.

    Everything else is optional, and also an ioctl on the nst device or a file of sysfs:

    - vendor, model:   /sys/class/scsi_tape/nstX/device/{vendor,model}, read by the kernel when it found the drive
    - serial:          INQUIRY, VPD page 0x80 (unit serial number), through SG_IO
    - tape inserted, write protect, LTO version: MTIOCGET. The LTO version is the SCSI density code of the medium (DENSITY), which is
      standardized; the medium type of MODE SENSE is not.

    *********************************************************************************************
    *   MANUAL OVERRIDE:                                                                        *
    *   Good News: You can always provide a manual override explicitly stating the LTO-Version. *
    *   When you override the LTO-Version the software assumes write-protect is off.            *
    *********************************************************************************************

    SOME tape drives show up as several scsi devices: my LTO8 is recognized either as /dev/st0 AND /dev/st1. The kernel
    reads the id of the logical unit (INQUIRY VPD page 0x83) and publishes it as wwid, see TD_Pool. An old drive (SCSI level SPC)
    may have none, e.g. the IBM ULTRIUM-TD3.

    Noteable Sources:
       primary source: (ISO/IEC 14776-453) https://www.t10.org/ftp/t10/document.08/08-309r1.pdf
       st(4), linux/mtio.h, linux/sg.h
    """

class TD_State(Enum):
    IDLE = 0
    QUEUED = 1      # orders wait in the Job queue
    REWIND = 2
    EJECT = 3
    WRITE = 4
    READ = 5
    ERROR = -1      # the last finished order failed
    NO_TAPE = -2    # the last rewind / eject found no tape
    BUSY = -3       # the last rewind / eject found the device opened by somebody else
    NOT_READY = -4  # the last rewind found the drive loading or unloading a tape

class TapeDrive:

    """
    ### === TapeDrive ====================================================

    A tape drive does four things, each one a step in the Job queue (returns the entry id, pass it
    as `dependsOn` to the next step):

    | `TapeDrive.`                  | SCSI / tool                                                     |
    |-------------------------------|-----------------------------------------------------------------|
    | `Rewind()`                    | `TapeIoctl.py rewind <nst>`, also the question whether the drive can take an order |
    | `Eject()`                     | `TapeIoctl.py eject <nst>`. Never part of a test.               |
    | `Write(source)`               | `dd if=<source> of=<nst>`: one tape file                        |
    | `Read(target)`                | `dd if=<nst> of=<target>`: the next tape file                   |
    | `WriteRandom(size, blocksize)` | incompressible test data to the tape, for the block size benchmark |

    **The OS only has to give:** the list of the nst devices, rewind, eject, `dd if=` and `dd of=`. Everything else (vendor,
    serial, LTO version, wwid, cartridge memory) is optional and must never stop a job. If the drive does not tell what
    tape is in it, the tape is `UNKNOWN` and the operator may describe it with `tapeOverride()`.

    **Never read at the end of the data.** The kernel driver (`st`) latches that and answers every
    later read with an I/O error until it is repositioned through the driver itself, as `Rewind()` does (a rewind with
    `sg_raw` does not help). `dd` opens the device blocking: without a tape it waits 2 minutes, so a
    job rewinds first. `dd` must also not use
    `iflag=fullblock` on the tape: after a short last block it swallows the file mark and goes on
    reading the next tape file. `Read()` therefore stops at the file mark by itself. Writing needs
    `conv=nocreat`: if the drive is gone `dd` would make a regular file `/dev/nstX` and fill the memory with it.

    Vendor, model (sysfs), serial and the tape (ioctls, see `refreshTape()`) are asked when it is created, not
    through `Job`. `state` is derived from the Job entries of the drive: `IDLE`, `QUEUED`, the running
    step (`REWIND`, `EJECT`, `WRITE`, `READ`), or if the last finished step failed `ERROR`, `NO_TAPE`, `BUSY` or `NOT_READY` (it loads or unloads).

    The two paths of a drive with two cables are in `paths`, the first one is used (see TD_Pool).
    `id` is the key the Job uses, one step at a time runs per id.

    Without SCSI tooling or hardware: `drive_override=True`, then set `rewindCommand` /
    `ejectCommand` (their command line is used for every step) and call `tapeOverride(Tape("8800", td.generic_path))`.
    `path` may then be a regular file, it has to exist. A regular file is truncated by every `Write()`, so only one
    tape file fits.

        >>> open("/tmp/fake", "ab").close()
        >>> td = TapeDrive("/tmp/fake", "", drive_override=True)
        >>> td.tapeOverride(Tape("8800", td.generic_path)); td.rewindCommand = Command("true")
        >>> step = td.Rewind()
        >>> step = td.Write("/tmp/some_file", dependsOn=step)
        >>> Job.Wait([step])
    """

    # System parameters (public)
    vendor: str = ""
    model: str = ""
    serial: str = ""
    blocksize: str = ""
    wwid: str = ""                  # kernel's id of the logical unit, the same on every path of one drive
    paths: List[Tuple[str, str]]    # all (nst, sg) device pairs of this drive, the first one is used

    rewindCommand: Command = None
    ejectCommand: Command = None

    # Internal variables, do not edit!
    drive_override: bool = False
    tape: Tape                      # per instance, see __init__
    tape_override: bool = False
    path: str = ""
    generic_path: str = ""
    command: Command = None         # the last Command of the drive
    error: str = ""                 # why INQUIRY failed, "" if it did not

    SYSFS: str = "/sys/class/scsi_tape"
    ASK_TIMEOUT: float = 2          # seconds to wait for the drive when it is asked something, a hung one must not hang us
    DENSITY: dict = {0x40: 1, 0x42: 2, 0x44: 3, 0x46: 4, 0x58: 5, 0x5A: 6, 0x5C: 7, 0x5D: 7, 0x5E: 8, 0x60: 9}     # 0x5D: LTO-7 M8
    TOC_BLOCK: str = "128K"         # a TOC is written like this, or smaller if the drive writes smaller blocks (tocBlock())
    READ_BLOCK: str = "256K"        # at least: a TOC is read before its header is known, and tapes up to 2026-11 have 256K blocks.
                                    # The drive hands out each block as it was written. Bigger than the limit of the
                                    # HBA fails (aic79xx: 4M works, 8M is EBUSY), smaller than the written block fails as well

    @staticmethod
    def sysfsRead(path: str, attribute: str, root: str = SYSFS) -> str:
        """What the kernel says about a /dev/nstX device (e.g. 'wwid', 'vendor'), '' if it says nothing."""
        if not path:
            return ""
        try:
            with open(os.path.join(root, os.path.basename(path), "device", attribute)) as f:
                return f.read().strip()
        except OSError:
            return ""

    def __init__(self, path: str, generic_path: str, drive_override: bool = False, blocksize: str = "128K",
                 paths: List[Tuple[str, str]] | None = None, wwid: str = ""):
        self.path = path
        self.generic_path = generic_path
        self.paths = paths or [(path, generic_path)]
        self.wwid = wwid or self.sysfsRead(path, "wwid")
        self.tape = Tape("0000", generic_path)
        self.drive_override = drive_override
        self.blocksize = blocksize
        self.entries: List[Tuple[TD_State, str]] = []   # (step, Job entry id), in the order added
        self._taken: set = set()                        # entries whose result is already taken over
        self._state: TD_State = TD_State.IDLE
        if not drive_override:
            self.refreshDrive()
            self.refreshTape()

    @property
    def id(self) -> str:
        """
        Identifies the drive, no matter which of its paths is used. Job allows one command per id.
        A drive that was listed twice (no wwid) has two ids: whether it can take an order is
        for the drive itself to say, see DESIGN.md.
        """
        return self.wwid or self.path

    @property
    def state(self) -> TD_State:
        self.refresh()
        return self._state

    # === THE FOUR STEPS ======================================================

    def Rewind(self, runlist: str = "", dependsOn: str = "", always: bool = False, prepare=None) -> str:
        cmd: Command = self._like(self.rewindCommand) or self._ioctl("rewind")
        return self._queue(TD_State.REWIND, cmd, runlist, dependsOn, always, prepare)

    def Eject(self, runlist: str = "", dependsOn: str = "", always: bool = False, prepare=None) -> str:
        cmd: Command = self._like(self.ejectCommand) or self._ioctl("eject")
        return self._queue(TD_State.EJECT, cmd, runlist, dependsOn, always, prepare)

    def _ioctl(self, operation: str) -> Command:
        return Command(Command.quote(sys.executable) + " " + Command.quote(TapeIoctl.__file__) + " " + operation + " " + Command.quote(self.path))

    def Write(self, source: str, size: int = -1, runlist: str = "", dependsOn: str = "", always: bool = False, prepare=None,
              blocksize: str = "") -> str:
        """
        One tape file: the content of `source`, in blocks of `blocksize` (default: that of the drive).
        `size` only serves the progress display.
        """
        cmd: Command = Command("dd if=" + Command.quote(source) + " of=" + Command.quote(self.path) + " " +
                               "iflag=fullblock conv=nocreat status=none bs=" + (blocksize or self.blocksize), filesize=size, env={"LC_ALL": "C"})
        return self._queue(TD_State.WRITE, cmd, runlist, dependsOn, always, prepare)

    def WriteRandom(self, size: int, blocksize: int, runlist: str = "", dependsOn: str = "", always: bool = False,
                    prepare=None) -> str:
        """
        About `size` bytes of incompressible test data (AES-CTR over zeros, a throw-away key from the
        environment) in blocks of `blocksize` bytes, for the block size benchmark. `dd` reports the speed and once
        per second the progress on stderr.
        """
        count: int = -(-size // blocksize)      # rounded up, the block size is what is tested
        cmd: Command = Command("openssl enc -aes-128-ctr -pbkdf2 -pass env:RUTBS_BENCH_KEY < /dev/zero 2>/dev/null | " +
                               "dd of=" + Command.quote(self.path) + " iflag=fullblock conv=nocreat status=progress bs=" + str(blocksize) + " count=" + str(count),
                               filesize=count * blocksize, env={"RUTBS_BENCH_KEY": os.urandom(16).hex(), "LC_ALL": "C"})
        return self._queue(TD_State.WRITE, cmd, runlist, dependsOn, always, prepare)

    def Read(self, target: str, size: int = -1, runlist: str = "", dependsOn: str = "", always: bool = False, prepare=None,
             count: int = 0, blocksize: str = "") -> str:
        """
        The next tape file, from the current position, into `target`. Ends at its file mark.
        `count` > 0 stops after that many blocks, for a tape file that may be something else than expected.
        `blocksize` is the one it was written with, `READ_BLOCK` is the minimum.
        """
        # No iflag=fullblock: it reads on behind the file mark. A buffer bigger than the written block is harmless.
        cmd: Command = Command("dd if=" + Command.quote(self.path) + " of=" + Command.quote(target) + " " +
                               "status=none bs=" + self.readBlock(blocksize) + (" count=" + str(count) if count else ""), filesize=size,
                               env={"LC_ALL": "C"})
        return self._queue(TD_State.READ, cmd, runlist, dependsOn, always, prepare)

    @staticmethod
    def blockBytes(blocksize: str) -> int:
        "`256K` -> 262144. It may come from the header of a tape and ends up in a command: nothing else is accepted."
        found = re.fullmatch(r"(\d{1,9})([KM]?)", blocksize)
        if not found or int(found.group(1)) == 0:
            raise ValueError("Not a block size: " + repr(blocksize))
        return int(found.group(1)) * {"": 1, "K": 1 << 10, "M": 1 << 20}[found.group(2)]

    def tocBlock(self) -> str:
        "The TOC has to be readable by everybody, but a drive may take nothing bigger than its own block size."
        return min(self.TOC_BLOCK, self.blocksize, key=self.blockBytes)

    @staticmethod
    def readBlock(blocksize: str = "") -> str:
        if blocksize and TapeDrive.blockBytes(blocksize) > TapeDrive.blockBytes(TapeDrive.READ_BLOCK):
            return blocksize
        return TapeDrive.READ_BLOCK

    # === STATE ===============================================================

    @staticmethod
    def _like(template: Command | None) -> Command | None:
        """An override is a template: every step needs its own Command, Job refuses the same object twice."""
        return None if template is None else Command(template.cmd, template.filesize, template.raw, dict(template.env))

    def _queue(self, step: TD_State, cmd: Command, runlist: str, dependsOn: str, always: bool, prepare) -> str:
        entry: str = Job.Add(cmd, tape=self.id, dependsOn=dependsOn, runlist=runlist, always=always, prepare=prepare)
        self.entries.append((step, entry))
        self.command = cmd
        return entry

    def refresh(self) -> None:
        """Derives the state from the Job entries and takes over what a finished step changed on the tape."""
        if not self.entries:
            return

        active: TD_State | None = None
        queued: bool = False
        failure: TD_State | None = None

        for step, entryId in self.entries:
            try:
                entry = Job.Get(entryId)
            except LookupError:
                continue    # Job was flushed

            if entry.state is EntryState.COMPLETED:
                failure = None
                if entryId not in self._taken:
                    self._taken.add(entryId)
                    self._takeOver(step)
            elif entry.state is EntryState.FAILED:
                failure = self._failure(step, entry.command.exitCode)
                if entryId not in self._taken:
                    self._taken.add(entryId)
                    if failure is TD_State.NO_TAPE:
                        self._noTape()
            elif entry.state is EntryState.RUNNING:
                active = step
                if step in {TD_State.WRITE, TD_State.READ}:
                    self.tape.begin_of_tape = False
            else:
                queued = True

        if active:
            self._state = active
        elif queued:
            self._state = TD_State.QUEUED
        else:
            self._state = failure or TD_State.IDLE

    @staticmethod
    def _failure(step: TD_State, exitCode: int) -> TD_State:
        if step in {TD_State.REWIND, TD_State.EJECT}:
            return {TapeIoctl.NO_MEDIUM: TD_State.NO_TAPE, TapeIoctl.BUSY: TD_State.BUSY, TapeIoctl.NOT_READY: TD_State.NOT_READY}.get(exitCode, TD_State.ERROR)
        return TD_State.ERROR

    def _noTape(self) -> None:
        self.tape.state = E_Tape.NO_TAPE
        self.tape.begin_of_tape = False
        self.tape_override = False

    def _takeOver(self, step: TD_State) -> None:
        match step:
            case TD_State.REWIND:
                self.tape.begin_of_tape = True
                if self.tape.state in {E_Tape.UNKNOWN, E_Tape.NO_TAPE, E_Tape.NOT_READY}:    # it can be rewound, so there is a tape
                    self.tape.state = E_Tape.ONLINE
            case TD_State.WRITE | TD_State.READ:
                self.tape.begin_of_tape = False
            case TD_State.EJECT:
                self._noTape()

    # === ASKING THE DRIVE ====================================================
    # In the process itself and not through Job: nothing here moves the tape, and Job's urgent commands stay with
    # the disks. A hung drive can not hang the caller: the ioctl runs in a thread that is given up after ASK_TIMEOUT.

    def _ask(self, question):
        """The answer of `question()`, None and a reason in `error` if it failed or took too long."""
        answer: list = []
        failure: list = []

        def run() -> None:
            try:
                answer.append(question())
            except Exception as ex:     # OSError: EBUSY while somebody else has the device, EIO if the drive refuses
                failure.append(str(ex))

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(self.ASK_TIMEOUT)
        if answer:
            return answer[0]
        self.error = failure[0] if failure else "no answer within " + str(self.ASK_TIMEOUT) + " s"
        return None

    def refreshDrive(self) -> None:
        """Vendor, model and serial. The drive works without them."""
        self.vendor = self.sysfsRead(self.path, "vendor") or self.vendor
        self.model = self.sysfsRead(self.path, "model") or self.model
        self.serial = self._ask(lambda: TapeIoctl.serial(self.path)) or ""

    def refreshTape(self) -> None:
        """
        What tape is in the drive (MTIOCGET). `UNKNOWN` if the drive does not tell (it is busy, or it is no real
        drive), `NO_TAPE` if the driver says so. An unknown density is a tape of an unknown LTO version.
        """
        if self.tape_override or self.drive_override:
            return
        status: dict | None = self._ask(lambda: TapeIoctl.status(self.path))
        if status is None:              # keep what is known
            if self.tape.state is E_Tape.NO_TAPE:
                self.tape.state = E_Tape.UNKNOWN
            return
        if status["noTape"]:
            self.tape = Tape("0000", self.generic_path)
            return
        if not status["online"]:        # neither ready nor empty: it loads or unloads, what it says about the tape means nothing
            self.tape = Tape("0000", self.generic_path)
            self.tape.state = E_Tape.NOT_READY
            return
        version: int = self.DENSITY.get(status["density"], 0)
        # Tape() takes the digits MODE SENSE used to give: LTO version, 8 = tape, 9 = write protected
        self.tape = Tape("%x8%s0" % (version, "9" if status["writeProtect"] else "1"), self.generic_path)
        self.tape.state = E_Tape.WRITE_PROTECT if status["writeProtect"] else E_Tape.ONLINE
        self.tape.begin_of_tape = status["beginOfTape"]
        self.tape.cartridgeMemory = CartridgeMemory(self.path, self.id)

    def requireTape(self) -> None:
        """Before a job: is there a tape? ValueError if not, or if the drive is not ready. `UNKNOWN` is no reason to refuse."""
        self.refreshTape()              # a tape may have been inserted since
        if self.tape.state is E_Tape.NO_TAPE:
            raise ValueError("No tape in the drive")
        if self.tape.state is E_Tape.NOT_READY:
            raise ValueError("The drive is loading or unloading a tape")

    def tapeOverride(self, _tape: Tape) -> None:
        self.tape_override = True
        self.tape = _tape

    # === SYSTEM ==============================================================

    def _asdict(self) -> dict:
        override: dict = {
            "active": self.drive_override
        }

        if self.rewindCommand is not None:
            override.update({"rewindCommand": self.rewindCommand._asdict()})

        if self.ejectCommand is not None:
            override.update({"ejectCommand" : self.ejectCommand._asdict()})

        data = {
            "environment": {
                "path": self.path,
                "generic_path": self.generic_path,
                "wwid": self.wwid,
                "paths": [{"path": p, "generic_path": g} for p, g in self.paths]},
            "drive_info": {
                "vendor": self.vendor,
                "model": self.model,
                "serial": self.serial },
            "override": override,
            "state": self.state.name,
            "error": self.error,
            "blocksize": self.blocksize,
            "tape": self.tape._asdict(),
            "command" : None if self.command is None else self.command._asdict()
        }

        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

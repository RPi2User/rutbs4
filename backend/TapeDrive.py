import json
import os
from time import sleep
from typing import List, Tuple
from enum import Enum

from backend.Command import Command
from backend.Job import EntryState, Job

from backend.Tape import Tape, E_Tape

"""_summary_
    
    -SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI-SCSI
    
    No we need to get our Hands VERY dirty.
    I'm trying my best to make this as easy as possible, you've been warned!
    
    The command 'sg_modes --raw /dev/sgX' returns the "Mode Parameter Header for Mode Sense (10)"
    This is a special data block used to show supported features.
    
    user@tape-server:~$ sg_modes --all /dev/sgX
            IBM       ULT3580-HH8       MA71   peripheral_type: tape [0x1]
        Mode parameter header from MODE SENSE(10):
        Mode data length=231, medium type=0x88, specific param=0x90, longlba=0
        Block descriptor length=8
        > General mode parameter block descriptors:
        Density code=0x5e
        00     5e 00 00 00 00 00 00 00

    This software uses just two fields (in regard of getting Tape information):
        medium type=0x88, specific param=0x90
    
    When medium type = 0 no tape is inserted. Specific param = 0x10 means no write protection
    medium type = 0xX8 the X shows the LTO-Version
    specific param = 0x90 means write protect.
    
    I know those assumptions are quite risky. But yet again: Nothing is standardized :c
    
    *********************************************************************************************
    *   MANUAL OVERRIDE:                                                                        *
    *   Good News: You can always provide a manual override explicitly stating the LTO-Version. *
    *   When you override the LTO-Version the software assumes write-protect is off.            *
    *********************************************************************************************
    
    For Drive Identification it's a mess as well.
    
    Problem:
    SOME tape drives are using multiple scsi devices for the same drive.
    Like: my LTO8 is recognized either as /dev/st0 AND /dev/st1. 
    This project supports multiple drives per System.
    
    Worst case:
    Someone bought 2 Drives of the same model. Sadly there is no standardized Field for the Serial Number.
    We need to be creative... A LOT...
    
    Lets start with an easy example:
    
        sg_raw -r 1k /dev/sgX 0x12 0 0 0 60 0
    
    This is a "INQUIRY". This command says the following:
        Please send Op-Code 0x12 to /dev/sgX, tell /dev/sgX that we want the first 96 (0x60) Bytes of Data.
        @sg_raw we just want to see the first 1000 Bytes of Data. Skip the rest.
        
    This command returns following:
    
    usr@tape-server:~$ sg_raw -r 1k /dev/sgX 0x12 0 0 0 60 0 
        SCSI Status: Good 

        Received 58 bytes of data:
        00     01 80 03 02 35 00 01 30  49 42 4d 20 20 20 20 20    ....5..0IBM     
        10     55 4c 54 52 49 55 4d 2d  54 44 33 20 20 20 20 20    ULTRIUM-TD3     
        20     35 43 4d 30 00 00 00 00  00 00 00 00 00 00 00 00    5CM0............
        30     00 00 00 00 00 00 00 00  0c 00                      ..........
        
    As you can see, the tape brive is happy with just 58 bytes of response data.
    So we can reduce the INQUIRY-Request to 58 bytes like this:
    
    usr@tape-server:~$ sg_raw -r 1k /dev/sgX 0x12 0 0 0 3A 0
    
    note that, our `-r 1k` stays untouched hence we only need it to specify our STDOUT buffer.
    But don't let yourself fool you from that conclusion.
    
    Only the INQUIRY part is specified, not the response length...
    
    usr@tape-server:~$ sg_raw -r 1k /dev/sgY 0x12 0 0 0 60 0
        SCSI Status: Good 

        Received 70 bytes of data:
        00     01 80 06 12 41 01 10 02  49 42 4d 20 20 20 20 20    ....A...IBM     
        10     55 4c 54 33 35 38 30 2d  48 48 38 20 20 20 20 20    ULT3580-HH8     
        20     4d 41 37 31 00 00 6a 00  00 00 00 00 00 00 00 00    MA71..j.........
        30     30 31 50 4c 33 31 37 20  00 00 00 a2 0c 28 04 60    01PL317 .....(.`
        40     05 20 0a 28 05 02                                   . .(..

    Here you can see the LTO8 Drive returned even more information than the LTO3 Drive.
    So keeping your constraints wide is always a good thing in research.
    
    I choose this command to fetch the inquiry data:
    
    usr@tape-server:~$ sg_raw -r 1k /dev/sgX 12 1 83 0 2a 0
    SCSI Status: Good 

        Received 42 bytes of data:
        00     01 83 00 26 02 01 00 22  49 42 4d 20 20 20 20 20    ...&..."IBM     
        10     55 4c 54 52 49 55 4d 2d  54 44 33 20 20 20 20 20    ULTRIUM-TD3     
        20     31 32 31 30 31 37 33 31  38 33                      1210173183
        
    This command get used to determine the Vendor, Model and Serial.
    Works on my two drives maybe work on others as well. Yet again: Noting is really standartized >.<
    
    Byte Explanation:
    
        0x12 -> INQUIRY
        0x01 -> EVPD (enable vital product data), this enables reading the following Page 
        0x83 -> Device Identification Page, this returns any Data used for the Drive ID
        0x00 -> Length High-Byte
        0x2a -> Length Low-Byte
        0x00 -> Control, no Control byte
    
    drive.vendor, drive.model and drive.serial got their value like that:
    
    Raw-Binary: `018300260201002249424d2020202020554c545249554d2d544433202020202031323130313733313833`
    Seperated into 16byte-Blocks:
        0183002602010022 49424d2020202020 -> First 8 Byte got discarded, lower 8 Bytes will be treated as "VENDOR" until first Space (0x20)
        554c545249554d2d 5444332020202020 -> All 16 Byte will be treated as "MODEL" until first SPACE
        3132313031373331 3833             -> All 10 Byte will be treated as "SERIAL".
        
    Note: After the 10 serial bytes (byte) IBM continues with very vendor specific stuff so we cut here.
    When those 10 Bytes cant be displayed as ASCII-String it'll be shown in hex. e.g.:
    
    - 31 FF 57 54 30 38 33 36 02 31 -> this will be "0x31ff5754303833360231"
    
    HOPEFULLY this is unique enough to differenciate between two idenitcal Models.
    
    Noteable Sources:
       primary source: (ISO/IEC 14776-453) https://www.t10.org/ftp/t10/document.08/08-309r1.pdf
       IBM: https://www.ibm.com/docs/en/ts4500-tape-library?topic=x5a-mode-parameter-header-mode-sense-10
    """

class TD_State(Enum):
    IDLE = 0
    QUEUED = 1      # orders wait in the Job queue
    REWIND = 2
    EJECT = 3
    WRITE = 4
    READ = 5
    ERROR = -1      # the last finished order failed

class TapeDrive:

    """
    ### === TapeDrive ====================================================

    A tape drive does four things, each one a step in the Job queue (returns the entry id, pass it
    as `dependsOn` to the next step):

    | `TapeDrive.`                  | SCSI / tool                                                     |
    |-------------------------------|-----------------------------------------------------------------|
    | `Rewind()`                    | `sg_raw <sg> 0x01 0 0 0 0 0` (REWIND)                           |
    | `Eject()`                     | `sg_raw <sg> 0x1B 0 0 0 0 0` (LOAD/UNLOAD). Never part of a test. |
    | `Write(source)`               | `dd if=<source> of=<nst>`: one tape file                        |
    | `Read(target)`                | `dd if=<nst> of=<target>`: the next tape file                   |

    All take `runlist=""`, `dependsOn=""`, `always=False` (closing step, runs even if its runlist was
    aborted) and `prepare=None` (called right before the step starts, see Job). Everything else is
    optional and not here (cartridge memory, seeking, formatting). No `mt`, SCSI only.

    The drive is asked for vendor / model / serial (INQUIRY) and the tape (MODE SENSE) when it is
    created. `state` is derived from the Job entries of the drive: `IDLE`, `QUEUED`, the running step
    (`REWIND`, `EJECT`, `WRITE`, `READ`), or `ERROR` if the last finished step failed.

    The two paths of a drive with two cables are in `paths`, the first one is used (see TD_Pool).
    `id` is the key the Job uses, one step at a time runs per id.

    Without SCSI tooling or hardware: `drive_override=True`, then set `rewindCommand` /
    `ejectCommand` (their command line is used for every step) and call `tapeOverride(Tape("8800"))`.
    `path` may then be a regular file. A regular file is truncated by every `Write()`, so only one
    tape file fits.

        >>> td = TapeDrive("/tmp/fake", "", drive_override=True)
        >>> td.tapeOverride(Tape("8800")); td.rewindCommand = Command("true")
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

    inquiryCommand: Command = None
    readModeSenseCommand: Command = None

    # Internal variables, do not edit!
    drive_override: bool = False
    tape: Tape                      # per instance, see __init__
    tape_override: bool = False
    path: str = ""
    generic_path: str = ""
    command: Command = None         # the last Command of the drive
    error: str = ""                 # why INQUIRY failed, "" if it did not

    SYSFS: str = "/sys/class/scsi_generic"

    @staticmethod
    def sysfsRead(generic_path: str, attribute: str, root: str = SYSFS) -> str:
        """What the kernel says about a /dev/sgX device (e.g. 'wwid'), '' if it says nothing."""
        if not generic_path:
            return ""
        try:
            with open(os.path.join(root, os.path.basename(generic_path), "device", attribute)) as f:
                return f.read().strip()
        except OSError:
            return ""

    def __init__(self, path: str, generic_path: str, drive_override: bool = False, blocksize: str = "256K",
                 paths: List[Tuple[str, str]] | None = None, wwid: str = ""):
        self.path = path
        self.generic_path = generic_path
        self.paths = paths or [(path, generic_path)]
        self.wwid = wwid or self.sysfsRead(generic_path, "wwid")
        self.tape = Tape("0000")
        self.drive_override = drive_override
        self.blocksize = blocksize
        self.entries: List[Tuple[TD_State, str]] = []   # (step, Job entry id), in the order added
        self._taken: set = set()                        # entries whose result is already taken over
        self._state: TD_State = TD_State.IDLE
        self._inquiry()
        self._readModeSense()

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
        cmd: Command = self._like(self.rewindCommand) or Command("sg_raw " + Command.quote(self.generic_path) + " 0x01 0 0 0 0 0")
        return self._queue(TD_State.REWIND, cmd, runlist, dependsOn, always, prepare)

    def Eject(self, runlist: str = "", dependsOn: str = "", always: bool = False, prepare=None) -> str:
        cmd: Command = self._like(self.ejectCommand) or Command("sg_raw " + Command.quote(self.generic_path) + " 0x1B 0 0 0 0 0")
        return self._queue(TD_State.EJECT, cmd, runlist, dependsOn, always, prepare)

    def Write(self, source: str, size: int = -1, runlist: str = "", dependsOn: str = "", always: bool = False, prepare=None) -> str:
        """One tape file: the content of `source`. `size` only serves the progress display."""
        cmd: Command = Command("dd if=" + Command.quote(source) + " of=" + Command.quote(self.path) + " " +
                               "iflag=fullblock status=none bs=" + self.blocksize, filesize=size)
        return self._queue(TD_State.WRITE, cmd, runlist, dependsOn, always, prepare)

    def Read(self, target: str, size: int = -1, runlist: str = "", dependsOn: str = "", always: bool = False, prepare=None) -> str:
        """The next tape file, from the current position, into `target`."""
        cmd: Command = Command("dd if=" + Command.quote(self.path) + " of=" + Command.quote(target) + " " +
                               "iflag=fullblock status=none bs=" + self.blocksize, filesize=size)
        return self._queue(TD_State.READ, cmd, runlist, dependsOn, always, prepare)

    # === STATE ===============================================================

    @staticmethod
    def _like(template: Command | None) -> Command | None:
        """An override is a template: every step needs its own Command, Job refuses the same object twice."""
        return None if template is None else Command(template.cmd, env=dict(template.env))

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
        lastFailed: bool = False

        for step, entryId in self.entries:
            try:
                entry = Job.Get(entryId)
            except LookupError:
                continue    # Job was flushed

            if entry.state is EntryState.COMPLETED:
                lastFailed = False
                if entryId not in self._taken:
                    self._taken.add(entryId)
                    self._takeOver(step)
            elif entry.state is EntryState.FAILED:
                lastFailed = True
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
            self._state = TD_State.ERROR if lastFailed else TD_State.IDLE

    def _takeOver(self, step: TD_State) -> None:
        match step:
            case TD_State.REWIND:
                self.tape.begin_of_tape = True
            case TD_State.WRITE | TD_State.READ:
                self.tape.begin_of_tape = False
            case TD_State.EJECT:
                self.tape.state = E_Tape.NO_TAPE
                self.tape.begin_of_tape = False
                self.tape_override = False

    # === ASKING THE DRIVE ====================================================

    def _inquiry(self) -> None:
        """
        > sg_raw -r 1k /dev/sgX 12 1 83 0 2a 0
        0183002602010022 49424d2020202020 -> First 8 Byte got discarded, lower 8 Bytes will be treated as "VENDOR" until first Space (0x20)
        554c545249554d2d 5444332020202020 -> All 16 Byte will be treated as "MODEL" until first SPACE
        3132313031373331 3833             -> All 10 Byte will be treated as "SERIAL".
        """
        # Do nothing if TapeDrive is unkown.
        if self.drive_override:
            return

        # Sensible to override
        if not self.inquiryCommand:
            self.command = Command("sg_raw --binary -r 1k " + Command.quote(self.generic_path) + " 12 1 83 0 2a 0", 0, True)
        else:
            self.command = self.inquiryCommand

        self.command.wait()

        for n in range(5):      # a drive that was just reset may need a moment
            if self.command.exitCode == 0 and self.command.stdout:
                break
            sleep(.5)
            self.command.reset()
            self.command.wait()

        if self.command.exitCode != 0 or not self.command.stdout:
            self.error = "INQUIRY failed: " + " ".join(self.command.stderr)
            self._state = TD_State.ERROR
            return

        ascii_id: str = bytes.fromhex(self.command.stdout[0]).decode("ascii", errors="replace")
        self.vendor = ascii_id[8:16].strip()
        self.model = ascii_id[16:31].strip()
        self.serial = ascii_id[32:42].strip()

    def _readModeSense(self) -> None:
        if self.tape_override or self.generic_path == "" or self.error:
            return

        # Sensible to override
        if not self.readModeSenseCommand:
            self.command = Command("sg_raw --binary -r 1k " + Command.quote(self.generic_path) + " 5a 0 0 0 0 0 0 0 4 0", 0, True)
        else:
            self.command = self.readModeSenseCommand

        self.command.wait()

        # When ModeSense needs an Inquiry than make one :3
        if self.command.exitCode == 6:
            self._inquiry()
            # Ugly, but I don't know "nicer" way currently
            self.command = Command("sg_raw --binary -r 1k " + Command.quote(self.generic_path) + " 5a 0 0 0 0 0 0 0 4 0", 0, True)
            self.command.wait()

        if self.tape.state == E_Tape.NO_TAPE:
            try:
                self.tape = Tape(self.command.stdout[0][4:])
            except IndexError:
                self.tape = Tape("0000")

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

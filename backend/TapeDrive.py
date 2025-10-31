import json
from time import sleep
from enum import Enum

from tbk.TableOfContent import TableOfContent
from backend.File import File
from backend.Command import Command

from backend.Tape import Tape, E_Tape

DEBUG: bool = False
VERSION = 4.1

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
    READ = 0,
    WRITE = 1,
    REWIND = 2,
    EJECT = 3,
    IDLE = 4,
    ERROR = -1

class TapeDrive:
    
    """_summary_
    Main Interfaces:
        - write(file: File)                 -> Main WRITE Command
        - read() -> List[Folder]            -> Main READ Command
        - writeInit(toc: TableOfContent)    -> rewinds tape and write TOC
        - readToc() -> TableOfContent       -> rewinds tape and returns TOC
        - clearErrorState() -> None:        -> User can clear Error, NOT SELF RESETTING!
    """
    
    vendor: str = ""
    model: str = ""
    serial: str = ""
    
    tape: Tape = Tape("0000")
    tape_override: bool = False
    
    state: TD_State = TD_State.ERROR
    path: str = ""
    generic_path: str = ""
    blocksize: str = ""
    command: Command = None
    file: File = None
    
    def _refresh(self) -> None:
        # When still initializing run first inquiry
        if self.command is None:
            self._inquiry()
            self._readModeSense()
            return
        
        # When currently running SOME stuff (except init)
        self.command.status()   # get current state
        
        # Don't interfere with running commands!
        if self.command.running:
            return

        # do not accept further commands when in error state
        if self.command.exitCode != 0:
            self.state = TD_State.ERROR
            return

        match self.state:
            case TD_State.REWIND: self.tape.begin_of_tape = True
            case TD_State.EJECT: 
                self.tape.state = E_Tape.NO_TAPE
                self.tape.begin_of_tape = False
        
        self.state = TD_State.IDLE
        self._inquiry()
        self._readModeSense()
        
    def _inquiry(self) -> None:
        """
        > sg_raw -r 1k /dev/sgX 12 1 83 0 2a 0
        0183002602010022 49424d2020202020 -> First 8 Byte got discarded, lower 8 Bytes will be treated as "VENDOR" until first Space (0x20)
        554c545249554d2d 5444332020202020 -> All 16 Byte will be treated as "MODEL" until first SPACE
        3132313031373331 3833             -> All 10 Byte will be treated as "SERIAL".
        """

        self.command = Command("sg_raw --binary -r 1k '" + self.generic_path +  "' 12 1 83 0 2a 0", 0, True)
        self.command.wait()
        
        if(self.command.exitCode != 0 or not self.command.stdout):
            self.command.wait()
            for n in range(5):
                if (self.command.exitCode == 0):
                    break
                sleep(.5)
                self.command.wait()
            self.state = TD_State.ERROR

        self.state = TD_State.IDLE
        
        self.vendor = bytes.fromhex(self.command.stdout[0]).decode("ascii", errors="replace")[8:16].strip()
        self.model = bytes.fromhex(self.command.stdout[0]).decode("ascii", errors="replace")[16:31].strip()
        self.serial = bytes.fromhex(self.command.stdout[0]).decode("ascii", errors="replace")[32:42].strip()

    def _readModeSense(self) -> None:
        
        if self.tape_override:
            return
        
        self.command = Command("sg_raw --binary -r 1k '" + self.generic_path +  "' 5a 0 0 0 0 0 0 0 4 0", 0, True)
        self.command.wait()
        
        # When ModeSense needs an Inquiry than make it :3
        if self.command.exitCode == 6:
            self._inquiry()

        if self.tape.state == E_Tape.NO_TAPE:
            try:
                self.tape = Tape(self.command.stdout[0][4:])
            except IndexError:
                self.tape = Tape("0000")

    def __init__(self, path: str, generic_path: str, blocksize: str = "256K"):
        self.path = path
        self.generic_path = generic_path
        self.blocksize = blocksize
        self.file = None
        self._refresh()
        
    def _asdict(self) -> dict:
        self._refresh()
        data = {
            "environment": {
                "path": self.path,
                "generic_path": self.generic_path},
            "drive_info": {
                "vendor": self.vendor,
                "model": self.model,
                "serial": self.serial },
            "state": self.state.name,
            "blocksize": self.blocksize,
            "command": self.command._asdict(),
            "tape": self.tape._asdict()
        }
        if self.file is None:
            data.update({"currentFile": None})
        else:
            data.update({"currentFile": self.file._asdict()})
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict())
    
    def tapeOverride(self, _tape: Tape) -> None:
        self.tape_override = True
        self.tape = _tape
        
    def clearError(self) -> None:
        self.state = TD_State.IDLE
        self.command = None

    def rewind(self) -> None: 
        self._refresh()
        if(self.state != TD_State.IDLE or self.tape.begin_of_tape):
            return
        self.__rewind()

    def eject(self) -> None:
        self._refresh()
        if self.state not in {TD_State.IDLE, TD_State.ERROR}:
            return
        self.__eject()

    def write(self, file: File):
        self._refresh()
        self.state = TD_State.WRITE

    def writeTOC(self, tableOfContent: TableOfContent):
        # This writes TOC as first File on Tape
        self._refresh()
        self.state = TD_State.WRITE

    def read(self, file: File):
        self._refresh()
        self.state = TD_State.READ

    def __eject(self):
        self.state = TD_State.EJECT
        self.command = Command("sg_raw '" + self.generic_path + "' 0x1B 0 0 0 0 0")
        self.command.start()
        self.tape_override = False

    def __rewind(self):
        self.state = TD_State.REWIND
        self.command = Command("sg_raw '" + self.generic_path + "' 0x01 0 0 0 0 0")
        self.command.start()
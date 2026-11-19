import json
from enum import Enum

from backend.CartridgeMemory import CartridgeMemory

class E_LTOv(Enum):
    NONE = 0
    LTO_1 = 1
    LTO_2 = 2
    LTO_3 = 3
    LTO_4 = 4
    LTO_5 = 5
    LTO_6 = 6
    LTO_7 = 7
    LTO_8 = 8
    LTO_9 = 9
    LTO_10 = 10
    LTO_11 = 11
    LTO_12 = 12
    LTO_13 = 13
    LTO_14 = 14
    LTO_15 = 15
    
    LTO_7_M8 = 0xff
    
class E_LTO_Cap(Enum):
    NONE = 0
    LTO_1 = 100 * 10**9
    LTO_2 = 200 * 10**9
    LTO_3 = 300 * 10**9
    LTO_4 = 800 * 10**9
    LTO_5 = 1500 * 10**9
    LTO_6 = 2500 * 10**9
    LTO_7 = 6 * 10**12
    LTO_8 = 12 * 10**12
    LTO_9 = 18 * 10**12
    LTO_10 = 30 * 10**12
    
    LTO_7_M8 = 9 * 10**12    # Not supported in Autodetect!

class E_Tape(Enum):
    NO_TAPE = 0
    WRITE_PROTECT = 1
    ONLINE = 2

class Tape():

    """#### === Tape ==========================================================
    This Class represents a physical tape.  
    In order to create a proper tape object you need a "hardware ID" and the generic SCSI device
    of the drive it sits in (a tape cannot exist without a drive), e.g. `Tape("8810", "/dev/sg12")`.  
    This ID is a 4-Char wide string containing the most important data:

        Tape("v8wx"):
        | Sym. | Description                |
        |------| ---------------------------|
        | v    | LTO Version in hexadecimal |
        | 8    | SCSI identifier for Tape   |
        | w    | WriteProtect: 9 = WP       |
        | x    | not used                   |

        Example: "3890" 
            str[0]: LTO-Version         → LTO-3
            str[1]: always 8 for Tape   → Valid Tape
            str[2]: 0bX001 when, X=1    → write protect enabled
            str[3]: not used

        Example: "8810" 
            str[0]: LTO-Version         → LTO-8
            str[1]: always 8 for Tape   → Valid Tape
            str[2]: 0bX001 when, X=0    → no write protect
            str[3]: not used
            
    Another important property is the blocksize. This parameter tells the system the optimal
    fragmentation for any read / write operation. This property is dependent on the Tape (not the Drive)

    #### === PARAMETER ========================================================

    | Tape.            | Type   | Description                                    |
    |------------------|--------|------------------------------------------------|
    | lto_version      | E_LTOv | Enum for the LTO Version, use NONE for Custom  |
    | native_capacity  | int    | Enum for current Capacity, NONE for Custom     |
    | write_protect    | bool   | Prevents tape of being over-written            |
    | begin_of_tape    | bool   | runtime parameter to keep track of rewinding   |
    | state            | E_Tape | Enum for basic state machine                   |
    | blocksize        | str    | Allows different blocksizes                    |
    | generic_path     | str    | Generic SCSI device of the drive               |
    | cartridgeMemory  | CartridgeMemory | The chip, read when a tape is in the drive |

    """

    def __init__(self, hardware_id: str, generic_path: str, blocksize: str = "256K")-> None:

        self.lto_version: E_LTOv = E_LTOv.NONE
        self.native_capacity: int = 0
        self.write_protect: bool = True
        self.begin_of_tape: bool = False
        self.state: E_Tape = E_Tape.NO_TAPE
        self.blocksize: str = blocksize
        self.generic_path: str = generic_path
        self.cartridgeMemory: CartridgeMemory = CartridgeMemory()      # reads the chip once a tape is in

        _lto_version: int = int(hardware_id[0], 16)
        self.write_protect = (int(hardware_id[2], 16) & 0x8 > 0) # Isolated bit 4
        type: int = int(hardware_id[1], 16)

        if self.lto_version == 0 and type == 0:
            self.state = E_Tape.NO_TAPE
            return

        if self.lto_version != 0 and type == 8:
            if (self.write_protect):
                self.state = E_Tape.WRITE_PROTECT
            else:
                self.state = E_Tape.ONLINE

        self.lto_version = E_LTOv(_lto_version)
        if self.lto_version.name in E_LTO_Cap.__members__:   # unknown capacity stays 0
            self.native_capacity = E_LTO_Cap[self.lto_version.name].value

        if generic_path and self.state in (E_Tape.ONLINE, E_Tape.WRITE_PROTECT):
            self.cartridgeMemory = CartridgeMemory(generic_path)

    def _asdict(self) -> dict:
        data = {
            "current_state": self.state.name,
            "lto-version": self.lto_version.name,
            "writeProtect": self.write_protect,
            "beginOfTape": self.begin_of_tape,
            "blocksize": self.blocksize,
        }
        if type(self.native_capacity) is int:
            data.update({"native_capacity": self.native_capacity})
        if type(self.native_capacity) is E_LTO_Cap:
            data.update({"native_capacity": self.native_capacity.value}) # type: ignore
        if type(self.cartridgeMemory) is CartridgeMemory:
            data.update({"cartridgeMemory": self.cartridgeMemory._asdict()})
        return data
    
    def __str__(self):
        return json.dumps(self._asdict(), indent=2)

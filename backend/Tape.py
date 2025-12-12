import json
from enum import Enum

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



    def __init__(self, hardware_id: str)-> None:

        """
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
        """

        self.lto_version: E_LTOv = E_LTOv.NONE
        self.native_capacity: E_LTO_Cap = E_LTO_Cap.NONE
        self.write_protect: bool = True
        self.begin_of_tape: bool = False
        self.state: E_Tape = E_Tape.NO_TAPE

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
        self.native_capacity = E_LTO_Cap[self.lto_version.name]
    
    
    def _asdict(self) -> dict:
        data = {
            "lto-version": self.lto_version.name,
            "native_capacity": self.native_capacity.value,
            "beginOfTape": self.begin_of_tape,
            "current_state": self.state.name
        }
        return data
    
    def __str__(self):
        return json.dumps(self._asdict())

import json
from typing import List
from tbk.TapeDrive import TapeDrive
from backend.Command import Command

class TD_Pool:
    
    c_list = Command("find /dev/sg* -maxdepth 1 -type c -group tape")
    c_val = Command("find /sys/class/scsi_generic/sg7/device/scsi_tape/nst? -maxdepth 0 ")
    
    drives: List[TapeDrive] = []
    
    def __init__(self):
        self.gatherDrives()
    
    def gatherDrives(self):
        self.c_list.start()
    
    def _asdict(self):
        data = {
            
        }
        return data
    
    def __str__(self):
        return json.dumps(self._asdict())

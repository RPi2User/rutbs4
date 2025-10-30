import json
from typing import List
from backend.TapeDrive import TapeDrive
from backend.Command import Command

class TD_Pool:
    
    c_list = Command("find /dev/sg* -maxdepth 1 -type c -group tape")
    c_val = Command("find /sys/class/scsi_generic/sg7/device/scsi_tape/nst? -maxdepth 0 ")
    
    message: str = ""
    
    drives: List[TapeDrive] = []
    
    def __init__(self):
        self.gatherDrives()
        
        for drive in self.drives:
            print(drive)
    
    def gatherDrives(self):
        self.c_list.start()
        if self.c_list.exitCode != 0 or self.c_list.stderr != []:
            self.message = "[INFO] No Drives Found"
            return
        for paths in self.c_list.stdout:
            _generic_path = paths
            _generic = paths.split("/")[-1]
            
            self.c_val = Command("find /sys/class/scsi_generic/" + _generic + "/device/scsi_tape/nst? -maxdepth 0")
            self.c_val.start()
            
            if self.c_val.exitCode != 0 or self.c_val.stderr != []:
                self.message = "[ERROR] Tape " + _generic_path + " not supported by Kernel!"
                return
            
            _path = "/dev/" + self.c_val.stdout[0].split("/")[-1]
            
            self.drives.append(TapeDrive(
                path =_path,
                generic_path = _generic_path
            ))
            
            
    
    def _asdict(self):
        data = {
            
        }
        return data
    
    def __str__(self):
        return json.dumps(self._asdict())

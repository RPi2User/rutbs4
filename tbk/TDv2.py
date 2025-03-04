import json
import os
import subprocess
from tbk import TableOfContent
from tbk import File

VERSION: int = 4

class TapeDrive:
    
    path : str
    ltoVersion : int
    status : int
    blockSize : str
    bsy : bool          # Only true when: R/W
    status_msg: str
    current_job: subprocess
    
    
    def __init__(self, path_to_tape_drive: str, blockSize: str = "1M") -> None:
        self.blockSize: str = blockSize
        self.path: str = path_to_tape_drive
        self.bsy = False
        self.status = self.getStatus()
    
    def eject(self) -> None:
        if self.getStatus() in {2,3,4} :
            os.system("mt -f " + self.path + " eject")

    def write(self, file: File) -> None:
        return # The following garbage is garbage
        _ec = os.system("dd if='" + file.path + "' of="+ self.path + " bs=" + self.blockSize + " 2>/dev/null")
        _ec = os.system("dd if='" + file.path + "' of="+ self.path + " bs=" + self.blockSize + " status=progress")
    
    def read(self, file: File) -> None:
        if self.status in {2,3,4}:
            
            self.status = 6
            self.bsy = True
            
            # Init Read
            exitCode = os.system("dd if='" + self.path + "' of='"+ file.path + "/" + file.name + "' bs=" + self.blockSize + " status=progress")
            # TODO: Change to subprocess for term/kill, dd-output → self.status_msg, exitcode handling
            
            self.bsy = False
            self.getStatus()
            
            # Errorhandling
            if exitCode != 0:
                self.status = 0 # Set status=0 to alarm user
                self.status_msg = "[ERROR] read failed, please re-insert the tape and try again! File: " + str(file)
            
    
    def rewind(self) -> None:
        self.getStatus()
        if self.status in {2,3,4}:
            os.system("mt -f " + self.path + " rewind")
    
    def readTOC(self) -> TableOfContent:
        pass
    
    def writeTOC(self, toc : TableOfContent) -> None:
        pass

    def getStatus(self) -> int:
        if self.bsy == False:
            try:
                _out : str = subprocess.run(["mt", "-f", self.path, "status"], capture_output=True, text=True).stdout.split("\n")[-2].split(" ")
            except:
                self.status_msg = "[ERROR] status-request failed: `mt '" + self.path + "' status` OUT: " + subprocess.run(["mt", "-f", self.path, "status"], capture_output=True, text=True).stdout
                return 0
            if 'ONLINE' in _out:
                if 'BOT' in _out:
                    if 'WR_PROT' in _out:
                        return 3        # Tape RDY + WP
                    return 2            # Tape RDY
                return 4                # Not at BOT, needs rewinding
            return 1                    # No Tape
        
        return self.status
    
        """_stati_
        0   Error
        1   No Tape
        2   Tape RDY
        3   Tape RDY + WP
        4   Not at BOT
        5   Writing
        6   Reading   
        
        255 notImplemented
        """
        
    def __str__(self) -> str:
        return "TapeDrive(Path: " + self.path + ", ltoVersion: " + str(self.ltoVersion) + ", Status: " + str(self.status) + ", BlockSize: " + self.blockSize + ", Busy?: " + str(self.bsy) + "\n"
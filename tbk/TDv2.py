import json
import os
import subprocess
import time
from tbk import TableOfContent
from tbk import File

VERSION: int = 4
DEBUG : bool = True


class TapeDrive:
    
    path : str
    ltoVersion : int
    status : int = 255
    blockSize : str
    bsy : bool          # Only true when: R/W
    status_msg: str = "NotInitialized"
    process: subprocess.Popen = None
    
    CMD_STATUS = "mt -f '{path}' status"
    CMD_EJECT = "mt -f '{path}' eject"
    CMD_REWIND = "mt -f '{path}' rewind"
    CMD_DD_READ = "dd if='{path}' of='{file_path}' bs='{block_size}' status=progress"
    CMD_DD_WRITE = "dd if='{file_path}' of='{path}' bs='{block_size}' status=progress"
    
    def __init__(self, path_to_tape_drive: str, blockSize: str = "1M") -> None:
        self.blockSize: str = blockSize
        self.path: str = path_to_tape_drive
        self.bsy = False
        self.status = self.getStatus()
    
    def eject(self) -> None:
        if self.getStatus() in {2,3,4} :
            self.bsy = True
            self.status = 8
            self.process = subprocess.Popen(self.CMD_EJECT.format(path=self.path), shell=True)

    def write(self, file: File) -> None:
        return # The following garbage is garbage        
    
    def read(self, file: File) -> None:
        self.status = self.getStatus()
        if self.status in {2, 3, 4}:
            self.status = 6  # Set status to "Reading"
            self.bsy = True
            self.process = subprocess.Popen(["dd", f"if={self.path}", f"of={file.path}/{file.name}", f"bs={self.blockSize}" ,"status=progress"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            # self.process.wait()
            # Errors need to be processed!
            print(self.process.stderr.read()) # FOR DEBUG PURPOSES ONLY
    
    def rewind(self) -> None:
        if self.getStatus() in {2,3,4}:
            self.bsy = True
            self.status = 7
            self.process = subprocess.Popen(self.CMD_REWIND.format(path=self.path), shell=True)
    
    def readTOC(self) -> TableOfContent:
        pass
    
    def writeTOC(self, toc : TableOfContent) -> None:
        pass

    def getStatusCleanup(self) -> None:
        """Cleans up the status message and resets the status message. Used when process finished unsuccessfull."""
        self.bsy = False
        self.status = self.getStatus()
        self.process = None

    def getStatus(self) -> int:     # Application must poll this fucker regularly!
        """Returns the current status of the tape drive."""
        if DEBUG: print("bsy: " + str(self.bsy) + " status: " + str(self.status) + " process: " + str(self.process))
        if self.bsy:
            match self.status:
                case 5: # Writing
                    if self.process.poll() is None:   # Check if process is still running
                        for line in iter(self.process.stderr.readline, ""):
                            self.status_msg = line
                            break
                        return 5
                    elif self.process.returncode != 0:
                        self.status_msg = "[ERROR] Write operation failed: " + self.process.stderr.read()
                        self.getStatusCleanup()
                        return 0
                    self.getStatusCleanup()

                case 6: # Reading
                    if self.process.poll() is None:   # Check if process is still running
                        for line in iter(self.process.stderr.readline, ""):
                            self.status_msg = line
                            break
                        return 6
                    elif self.process.returncode != 0:
                        self.status_msg = "[ERROR] Read operation failed: " + self.process.stderr.read()
                        self.getStatusCleanup()
                        return 0
                    self.getStatusCleanup()

                case 7: # Rewinding, needs different kind of handling, 'cause mt is weird
                    if self.process.poll() is None: return 7
                    self.getStatusCleanup()

                case 8: # Ejecting, analog to rewinding
                    if self.process.poll() is None: return 8
                    self.getStatusCleanup()    
                    
        else: # bsy == False / default behavior
            try:
                _out : str = subprocess.run(["mt", "-f", self.path, "status"], capture_output=True, text=True).stdout.split("\n")[-2].split(" ")
            except:
                self.status_msg = "[ERROR] status-request failed: `mt '" + self.path + "' status` OUT: " + subprocess.run(["mt", "-f", self.path, "status"], capture_output=True, text=True).stdout
                return 0
            self.status_msg = ""
            if 'ONLINE' in _out:
                if 'BOT' in _out:
                    if 'WR_PROT' in _out:
                        return 3        # Tape RDY + WP
                    return 2            # Tape RDY
                return 4                # Not at BOT, needs rewinding
            return 1                    # No Tape
        
        return 0                        # General Error
    
    def getStatusJson(self) -> json:
        """Returns the current status and status message as a JSON string."""
        status = self.getStatus()
        status_json = {
            "status": status,
            "statusMsg": self.status_msg
        }
        return status_json
    
    """_stati_
    0   Error
    1   No Tape
    2   Tape RDY
    3   Tape RDY + WP
    4   Not at BOT
    5   Writing
    6   Reading
    7   ejecting
    8   rewinding   
    
    255 notImplemented
    """
    
    def cancelOperation(self) -> None:
        """Cancels the current operation if a process is running."""
        if self.process and self.process.poll() is None:  # Check if process is still running
            self.process.terminate()  # Terminate the process
            try:
                self.process.wait(timeout=10)  # Wait for the process to terminate, with a timeout of 10 seconds
            except subprocess.TimeoutExpired:
                self.process.kill()  # Force terminate the process if it does not terminate within the timeout
                self.process.wait()  # Wait for the process to be killed

            if self.status == 5:
                self.status_msg += "\n[INFO] Write operation terminated by user."
            elif self.status == 6:
                self.status_msg += "\n[INFO] Read operation terminated by user."
            self.bsy = False
            self.status = self.getStatus()  # Update status
            self.process = None  # Reset the process
    
    def __str__(self) -> str:
        return "TapeDrive(Path: " + self.path + ", ltoVersion: " + str(self.ltoVersion) + ", Status: " + str(self.status) + ", BlockSize: " + self.blockSize + ", Busy?: " + str(self.bsy) + "\n"
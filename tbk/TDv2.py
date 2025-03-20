import json
import os
import subprocess
import uuid
import threading

import xml.etree.ElementTree as ET

from tbk.TableOfContent import TableOfContent
from tbk.File import File

VERSION: int = 4
DEBUG : bool = True

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

class TapeDrive:
    
    path : str
    ltoVersion : int
    status : int = 255
    blockSize : str
    bsy : bool          # Only true when: R/W
    status_msg: str = "NotInitialized"
    process: subprocess.Popen = None
    
    readThread: threading.Thread = None
    writeThread: threading.Thread = None
    
    CMD_STATUS = "mt -f '{path}' status"
    CMD_EJECT = "mt -f '{path}' eject"
    CMD_REWIND = "mt -f '{path}' rewind"
    CMD_DD_READ = "dd if='{path}' of='{file_path}' bs='{block_size}' status=progress"
    CMD_DD_WRITE = "dd if='{file_path}' of='{path}' bs='{block_size}' status=progress"
    
    def __init__(self, path_to_tape_drive: str, blockSize: str = "1M", ltoVersion: int = 0) -> None:
        if DEBUG: print("[INIT] TapeDrive.__init__() " + path_to_tape_drive + " " + blockSize + " " + str(ltoVersion)) 
        self.ltoVersion = ltoVersion
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
        
            def read_thread(self):
                for line in iter(self.process.stderr.readline, ""):
                    self.status_msg = line
            
            readThread = threading.Thread(target=read_thread(self), daemon=True)
            readThread.start()
        

    
    def rewind(self) -> None:
        if self.getStatus() in {2,3,4}:
            self.bsy = True
            self.status = 7
            self.process = subprocess.Popen(self.CMD_REWIND.format(path=self.path), shell=True)
    
    def readTOC(self) -> TableOfContent:
        if self.status in {2, 3}: # RDY or RDY + WP
            toc_uuid : str = str(uuid.uuid4())
            toc_filename : str = "toc_" + toc_uuid + ".tmp"
            file : File = File(0, toc_filename, "/tmp")
            
            self.read(file)
            toc : TableOfContent = self.xml2toc(file)
            self.showTOC(toc)
            #os.remove(file.fullPath)
        
            pass
    
    def writeTOC(self, toc : TableOfContent) -> None:
        pass

    def getStatusCleanup(self) -> None:
        """Cleans up the status message and resets the status message. Used when process finished unsuccessful."""
        self.bsy = False
        self.process = None
        self.status = self.getStatusFromMT()

    def getStatusFromMT(self) -> int:
        """Returns the current status of the tape drive based on the 'mt' command."""
        try:
            # This is very fucky string manipulation so it needs special treatment ^^
            _out : str = subprocess.run(["mt", "-f", self.path, "status"], capture_output=True, text=True).stdout.split("\n")[-2].split(" ")
        except:
            self.status_msg = "[ERROR] status-request failed: `mt '" + self.path + "' status` OUT: " + subprocess.run(["mt", "-f", self.path, "status"], capture_output=True, text=True).stdout
            return 0
        # self.status_msg = "" # Clear last status message
        if 'ONLINE' in _out:
            if 'BOT' in _out:
                if 'WR_PROT' in _out:
                    return 3        # Tape RDY + WP
                return 2            # Tape RDY
            return 4                # Not at BOT, needs rewinding
        return 1                    # No Tape

    def getStatusWhenBsy(self) -> int: # When bsy then is EITHER process currently running OR finished
        # Process is terminated when self.process.poll() is not None -> has Exitcode
        
        if self.process.poll() is not None:  # if Process is terminated
            proc_exit_code = self.process.returncode # Keep Exit-Code
            self.getStatusCleanup() # Cleanup
            
            if proc_exit_code != 0: # Eval EC
                self.status_msg = "[ERROR] Operation at Status" + str(self.status) + " failed with exitcode: " + str(proc_exit_code)
                self.status = 0 # Set ERROR state
                
        return self.status

    def getStatus(self) -> int: # Application must poll this fucker regularly :)
        if self.bsy:
            return self.getStatusWhenBsy()
        else:
            return self.getStatusFromMT()
    
    def getStatusJson(self) -> json:
        """Returns the current status and status message as a JSON string."""
        status: int = self.getStatus()
        status_json: json = {
            "status": status,
            "statusMsg": self.status_msg
        }
        return status_json
    
    def xml2toc(self, file: File) -> TableOfContent: # Imported from legacy TapeDrive.py 
        self.rewind()
        # Read XML from Tape
        self.read(file)
        # Try to parse File
        try:
            xml_root: ET.Element = ET.parse(source=file.fullPath).getroot()
        except: #TODO add to self.status_msg
            print("[ERROR] Could not parse Table of Contents: Invalid Format")
            print("Try 'tbk --dump | tbk -d'")
        files: list[File] = []
        for index in range(1, len(xml_root)):
            try:                
                files.append(File(id=int(str(xml_root[index][0].text)),
                                name=str(xml_root[index][1].text),
                                path=str(xml_root[index][2].text),
                                size=int(str(xml_root[index][3].text)),
                                cksum_type=str(xml_root[index][4].text),
                                cksum=str(xml_root[index][5].text)
                ))
            except:
                files.append(File(id=int(str(xml_root[index][0].text)),
                                name=str(xml_root[index][1].text),
                                path=str(xml_root[index][2].text),
                                size=int(str(xml_root[index][3].text))
                ))
        _out: TableOfContent = TableOfContent(
            files=files,
            lto_version=str(xml_root[0][0].text),
            optimal_blocksize=str(xml_root[0][1].text),
            tape_sizeB=int(str(xml_root[0][2].text)),
            tbk_version=str(xml_root[0][3].text),
            last_modified=str(xml_root[0][4].text)
        )
        return _out
    
    def showTOC(self, toc: TableOfContent) -> None:
        # User-Readable listing from Contents of Tape
        print("\n--- TAPE INFORMATION ---\n")
        print("- TBK-Version:\t" + toc.tbkV)
        print("- LTO-Version:\t" + toc.ltoV)
        print("- Blocksize:\t" + toc.bs)
        print("- Tape-Size:\t" + str(toc.tape_size))
        print("\nLast Modified:\t" + toc.last_mod)
        print("\n*")
        _remaining: int = toc.tape_size
        for file in toc.files:
            print("├─┬ \x1b[96m" + file.name + "\x1b[0m")
            print("│ ├── Size:\t" + str(file.size))
            print("│ └── Checksum:\t" + file.cksum)
            print("│")
            _remaining -= file.size
        print("│")
        print("└ \x1b[93m" + str(_remaining) + "\x1b[0m Remaining")
    
    # NEEDS REFACTOR! -> Test ok by e18f99a74b1452e3a5b1ac2d7a23a43b13cce10a 
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
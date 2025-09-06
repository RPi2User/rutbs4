from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import json
import os

import subprocess
import uuid
import threading

import xml.etree.ElementTree as ET
from tbk.TableOfContent import TableOfContent
from tbk.File import File
from tbk.Status import Status
from tbk.Checksum import Checksum

from time import sleep
from functools import partial

VERSION: int = 4
DEBUG : bool = True

"""__TODOs__

Features:

- Add method waitUntilFinished(Status) -> None;
    This will reduce recurring Code
    
Bugs:

- Check after every operation if current status is Status.ERROR and cancel current operation

"""

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
    currentID: int = -1
    process: subprocess.Popen = None
    coreCount: int = os.cpu_count()
    
    checksumming: bool = True
    
    readThread: threading.Thread = None
    writeThread: threading.Thread = None
    
    CMD_STATUS = "mt -f '{path}' status"
    CMD_EJECT = "mt -f '{path}' eject"
    CMD_REWIND = "mt -f '{path}' rewind"
    CMD_DD_READ = "dd if='{path}' of='{file_path}' bs='{block_size}' status=progress"
    CMD_DD_WRITE = "dd if='{file_path}' of='{path}' bs='{block_size}' status=progress"
    
    def __init__(self, path_to_tape_drive: str, blockSize: str = "1M", ltoVersion: int = 0) -> None:
        self.status_msg = "Initializing..."
        self.ltoVersion = ltoVersion
        self.blockSize: str = blockSize
        self.path: str = path_to_tape_drive
        self.bsy = False
        self.status = self.getStatus()
    
    def eject(self) -> None:
        if self.getStatus() in {Status.TAPE_RDY.value, Status.TAPE_RDY_WP.value, Status.NOT_AT_BOT.value}:
            self.bsy = True
            self.status = Status.EJECTING.value
            self.status_msg = "Ejecting..."
            self.process = subprocess.Popen(self.CMD_EJECT.format(path=self.path), shell=True)

    def write(self, file: File) -> None:
        self.status = self.getStatus()
        if DEBUG: print("[WRITE] " + str(file))
        
        
        while self.status is Status.WRITING.value:
            sleep(0.1)  # Wait for the write-process to finish
            self.status = self.getStatus()
            
        if self.status in {Status.TAPE_RDY.value, Status.NOT_AT_BOT.value}:
            self.status = Status.WRITING.value
            self.bsy = True
            #if DEBUG: print("DD-CMD: dd if='" + file.path + "' of='" + self.path + "' bs='" + self.blockSize + "' status=progress")
            self.process = subprocess.Popen(["dd", f"if={file.path}", f"of={self.path}", f"bs={self.blockSize}" ,"status=progress"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            def write_thread(self):
                for line in iter(self.process.stderr.readline, ""):
                    self.currentID = file.id
                    self.status_msg = line
            
            writeThread = threading.Thread(target=write_thread(self), daemon=True)
            writeThread.start()
        else:
            print("[ERROR] Write operation failed, Tape in incorrect state! " + str(self.status))
    
    def writeTape(self, toc: TableOfContent, eject: bool = False) -> int:
        # Check whether tape is large enough for toc.files[] -> 423
        # Generate Checksums        -> 500
        # Write TOC to tape         -> 500
        # Write files to tape       -> 500
        # Rewind tape
        # Eject tape if requested   -> 200
        
        # Init of TapeDrive to prepare for writing
        if self.status is Status.TAPE_RDY_WP.value:
            self.status = Status.ERROR.value
            self.status_msg = "[ERROR] Tape is write-protected!"
            return 409
        
        if self.status is Status.NOT_AT_BOT.value:
            self.rewind()
            while self.status == Status.REWINDING.value:
                sleep(0.1)
                self.status = self.getStatus()
                
        if self.status is Status.TAPE_RDY.value: pass
        # Drive should be ready now
        if self.checksumming: 
            _out: bool = self.calcChecksums(toc, readWrite=False) # Create checksums
                
        else: 
            self.status = Status.ERROR.value
            self.status_msg = "[ERROR] System could not prepare Drive for write process!"
            return 500
        
        self.writeTOC(toc) # Write TOC to tape
        
        for file in toc.files:
            self.write(file)
            
        self.rewind()
        while self.status == Status.REWINDING.value:
            sleep(0.1)
            self.status = self.getStatus()
        
        if eject:
            self.eject()
            while self.status == Status.EJECTING.value:
                sleep(0.1)
                self.status = self.getStatus()

        return 200
    
    def read(self, file: File) -> None: # we let this crash, exception handling is done in readTape and readTOC
        self.status = self.getStatus()
        if DEBUG: print("[READ] " + str(file))
        if self.status in {Status.TAPE_RDY.value, Status.TAPE_RDY_WP.value, Status.NOT_AT_BOT.value}:
            self.status = Status.READING.value
            self.bsy = True
            self.process = subprocess.Popen(["dd", f"if={self.path}", f"of={file.path}", f"bs={self.blockSize}" ,"status=progress"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
            def read_thread(self):
                for line in iter(self.process.stderr.readline, ""):
                    self.currentID = file.id
                    self.status_msg = line
            
            readThread = threading.Thread(target=read_thread(self), daemon=True)
            readThread.start()
        
    def readTOC(self, destPath="/tmp") -> TableOfContent:
        self.rewind()
        while self.status == Status.REWINDING.value:
            sleep(0.1)
            self.status = self.getStatus()
        toc_uuid : str = str(uuid.uuid4())
        toc_filename : str = "toc_" + toc_uuid + ".tmp"
        
        if destPath != "/tmp":
            try:
                os.makedirs(destPath, exist_ok=True)
            except Exception as e:
                self.status = Status.ERROR.value
                self.currentID = -1
                self.status_msg = "[ERROR] Insufficient Permissions on directory: " + destPath + "\nException: " + str(e)
                return None
        
        file : File = File(0, toc_filename, destPath + "/" + toc_filename, Checksum())
        
        self.read(file)
        while(self.bsy):
            sleep(0.1)  # Wait for the read-process to finish
            self.status = self.getStatus()
        file_list: list[File] = [file]

        toc : TableOfContent = TableOfContent(file_list, "", "")
        self.status_msg = toc.xml2toc(file)
        if self.status_msg != "Success":
            self.status = Status.ERROR.value
            return None
        if DEBUG: print(str(toc))
        if destPath == "/tmp":  # Backend should/can not delete file in foreign directory
            os.remove(file.path)
        
        return toc
    
    
    def readTape(self, toc: TableOfContent, dest_path: str) -> TableOfContent:
        
        if toc.files[0].cksum.value == "00000000000000000000000000000000": self.checksumming = False
        
        # read entire tape to dest_path
        self.rewind()
        if self.getStatus() in {Status.REWINDING.value}:
            while self.status == Status.REWINDING.value:
                sleep(0.1) # Wait for the rewind-process to finish
                self.status = self.getStatus()
                
        if self.getStatus() in {Status.TAPE_RDY.value, Status.TAPE_RDY_WP.value}: # All conditions met
            self.readTOC(destPath=dest_path) # Put TOC in dest_path
            # Tape moved from BOT to File 1
            if self.status == Status.ERROR.value: return None # TOC-Read is failed
            for file in toc.files:
                file.path = dest_path + "/" + file.name # Set the destination path
                
                try:
                    self.read(file)
                except Exception as e:
                    self.status = Status.ERROR.value
                    self.status_msg = "[ERROR] Read operation failed: " + str(e) + " at " + str(file)
                    self.currentID = -1
                    return None
                
                while(self.bsy):
                    sleep(0.1)
                    self.status = self.getStatus()

        # Read completed
        self.currentID = -1
        if self.checksumming:
            # Check on demand
            if not self.calcChecksums(toc, readWrite=True): return None
            
        self.rewind()
        while self.status == Status.REWINDING.value:
            sleep(0.1) # Wait for the rewind-process to finish
            self.status = self.getStatus()
            
        # When all is done, we can return a toc
        return toc
    
    def writeTOC(self, toc : TableOfContent) -> None:
        self.rewind()
        while self.status == Status.REWINDING.value:
            sleep(0.1)
            self.status = self.getStatus()
        toc_uuid : str = str(uuid.uuid4())
        toc_filename : str = "toc_" + toc_uuid + ".tmp"
        toc_path: str = "/tmp/" + toc_filename
        tocfile: File = File(0, toc_filename, toc_path, Checksum())
        current_xml: ET.ElementTree = self.toc2xml(toc)
        current_xml.write(tocfile.path, encoding="utf-8", xml_declaration=True)

        self.write(tocfile)
        
        os.remove(tocfile.path)
    
    def rewind(self) -> None:
        if self.getStatus() in {Status.TAPE_RDY.value, Status.TAPE_RDY_WP.value, Status.NOT_AT_BOT.value}:
            self.bsy = True
            self.status = Status.REWINDING.value
            self.status_msg = "Rewinding..."
            self.process = subprocess.Popen(self.CMD_REWIND.format(path=self.path), shell=True)

    def getStatusCleanup(self) -> None:
        """Used when process finished successful. Do some cleanup."""
        self.bsy = False
        self.process = None
        self.status_msg = ""
        self.currentID = -1
        self.status = self.getStatusFromMT()

    def getStatusFromMT(self) -> int:
        """Returns the current status of the tape drive based on the 'mt' command."""
        try:
            # This is very fucky string manipulation so it needs special treatment ^^ (exception handling)
            _out : str = subprocess.run(["mt", "-f", self.path, "status"], capture_output=True, text=True).stdout.split("\n")[-2].split(" ")
            self.status_msg = _out
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
        #status: int = self.getStatus() #BUG Some code relies on this being called
        status_json: json = {
            "status": self.status,
            "statusMsg": self.status_msg,
            "currentFileID": self.currentID,
        }
        return status_json
    
    def getTapeDriveJSON(self) -> json:        # This will return a JSON in favor of plain text
        tape_json: json = {
            "TapeDrive": {
                "path" : self.path,
                "ltoVersion" : self.ltoVersion,
                "status" : self.status,
                "blockSize" : self.blockSize,
                "bsy?" : self.bsy
            }
        }
        return tape_json

    
    def toc2xml(self, toc: TableOfContent) -> ET.ElementTree: # Imported from legacy TapeDrive.py
        # Create XML-Root
        root = ET.Element("toc")
        # Append Header
        header: ET.Element = ET.SubElement(root, "header")
        ET.SubElement(header, "lto-version").text = str(toc.ltoV)
        ET.SubElement(header, "optimal-blocksize").text = toc.bs
        ET.SubElement(header, "tape-size").text = str(toc.tape_size)
        ET.SubElement(header, "tbk-version").text = str(VERSION)
        ET.SubElement(header, "last-modified").text = str(datetime.datetime.now())
        # Append Files
        for entry in toc.files:
            file: ET.Element = ET.SubElement(root, "file")
            ET.SubElement(file, "id").text = str(entry.id)
            ET.SubElement(file, "filename").text = entry.name
            ET.SubElement(file, "complete-path").text = entry.path
            ET.SubElement(file, "size").text = str(entry.size)
            ET.SubElement(file, "type").text = entry.cksum.type
            ET.SubElement(file, "value").text = entry.cksum.value
        
        xml_tree: ET.ElementTree = ET.ElementTree(element=root)
        ET.indent(tree=xml_tree)
        return xml_tree
        
    
    def calcChecksums(self, toc: TableOfContent, readWrite: bool) -> bool:
        max_threads = self.coreCount  # get the number of CPU threads
        _out: bool = True
        with ThreadPoolExecutor(max_threads) as executor:
            future_to_file = {executor.submit(partial(file.CreateChecksum, readWrite)): file for file in toc.files}
            
            for future in as_completed(future_to_file):
                file: File = future_to_file[future]
                try:
                    success = future.result()  # Wait for the checksum calculation to finish and get the result
                    if not success: 
                        self.status_msg = "[ERROR] Checksum MISMATCH for " + str(file)
                        self.status = Status.ERROR.value
                        _out = False
                except Exception as e:
                    self.status_msg = f"[ERROR] Exception during checksum calculation for {file}: {e}"
                    self.status = Status.ERROR.value
                    _out = False
        return _out
    
    # NEEDS REFACTOR! -> Test ok by e18f99a74b1452e3a5b1ac2d7a23a43b13cce10a 
    def cancelOperation(self) -> None:
        """Cancels the current operation if a process is running."""
        while self.process and self.process.poll() is None:  # Check if process is still running
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
            sleep(0.5)

    # TODO conv to json OR _asdict()
    def __str__(self) -> str:
        return "TapeDrive(Path: " + self.path + ", ltoVersion: " + str(self.ltoVersion) + ", Status: " + str(self.status) + ", BlockSize: " + self.blockSize + ", Busy?: " + str(self.bsy) + "\n"

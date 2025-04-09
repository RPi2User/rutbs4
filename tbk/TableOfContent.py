import json
import os
import xml.etree.ElementTree as ET
from tbk.File import File
from tbk.Checksum import Checksum
from datetime import datetime

DEBUG: bool = True
VERSION: str = "4.0.0"

class TableOfContent:

    files: list[File]
    ltoV : int
    bs: str
    tape_size : int
    tbkV : str
    last_mod : str
    create_cksum: bool = True

    def __init__(self, files: list[File], lto_version: int, optimal_blocksize: str, tbk_version: str = VERSION, last_modified: str = "", createChecksum = True) -> None:
        
        if files is []: return None         # Return None if no files are given
        self.files: list[File] = files      # List of all Files from TableOfContent
        self.ltoV: int = lto_version        # LTO-Version of Tape/Drive
        self.bs: str = optimal_blocksize    # Optimal Blocksize
        self.tape_size: int = self.get_tape_size_from_json()    # Constant, depends on LTO-Version
        self.tbkV: str = tbk_version        # Software-Version of Tape-Backup-Software from original TOC
        self.last_mod: str = last_modified  # Optional Timestamp (required for reading of tape)
        self.create_cksum: bool = createChecksum # Optional Checksum-Flag (required for writing to tape)
        
        
    def calcChecksums(self) -> None: # Need to implement parallel checksumming based on CPU-Core-Count. (host.get_cpu_cores())
        pass
    
    def xml2toc(self, file: File) -> str:
        try:    # Try to parse File
            xml_root: ET.Element = ET.parse(source=str(file.path)).getroot()
        except:
            if DEBUG: print("[ERROR] Could not parse Table of Contents: Invalid Format")
            return "[ERROR] Could not parse Table of Contents: Invalid Format"
        self.files: list[File] = []
        for index in range(1, len(xml_root)):
            try:                
                self.files.append(File(id=int(str(xml_root[index][0].text)),
                                name=str(xml_root[index][1].text),
                                path=str(xml_root[index][2].text),
                                cksum = Checksum(value=str(xml_root[index][5].text),
                                         type=str(xml_root[index][4].text)),
                                size=int(str(xml_root[index][3].text))
                ))
            except:
                self.files.append(File(id=int(str(xml_root[index][0].text)),
                                name=str(xml_root[index][1].text),
                                path=str(xml_root[index][2].text),
                                size=int(str(xml_root[index][3].text))
                ))
        
        self.ltoV = int(xml_root[0][0].text)
        self.tape_size = self.get_tape_size_from_json()
        self.bs = str(xml_root[0][1].text)
        self.tbkV = str(xml_root[0][3].text)
        self.last_mod = str(xml_root[0][4].text)
    
        return "Success"

    def get_tape_size_from_json(self) -> int:
        """_summary_
            rbs_ltoV.json is a JSON file that contains the LTO-Standards and their respective capacities.
            The function reads the JSON file and returns the capacity in bytes for the given LTO version.
            The JSON file is located in the same directory as this script.
        Returns:
            int: Capacity in bytes for the given LTO version.
        """
        script_dir = os.path.dirname(__file__)  # Get the directory of the current script
        json_path = os.path.join(script_dir, 'rbs_ltoV.json')  # Construct the relative path
        with open(json_path, 'r') as f:
            
            lto_db = json.load(f)
            for standard in lto_db["LTO_Standards"]:
                if standard["Generation"] == self.ltoV:
                    return standard["capacityInBytes"]
        return 0  # Default value if not found
    
    def showTOC(self) -> str:
        # User-Readable listing from Contents of Tape
        toc_str = "\n--- TAPE INFORMATION ---\n"
        toc_str += "- TBK-Version:\t" + self.tbkV + "\n"
        toc_str += "- LTO-Version:\t" + str(self.ltoV) + "\n"
        toc_str += "- Blocksize:\t" + self.bs + "\n"
        toc_str += "- Tape-Size:\t" + str(self.tape_size) + "\n"
        toc_str += "\nLast Modified:\t" + self.last_mod + "\n"
        toc_str += "\n*"
        _remaining: int = self.tape_size
        for file in self.files:
            toc_str += "\n├─┬ \x1b[96m" + file.name + "\x1b[0m"
            if file.cksum.value != "00000000000000000000000000000000":
                toc_str += "\n│ ├── Size:\t" + str(file.size)
                toc_str += "\n│ └── Checksum:\t" + file.cksum.value
                
            else :
                toc_str += "\n│ └── Size:\t" + str(file.size)           # Uses suitable Border-Chars when Checksum is not available
            toc_str += "\n│"
            _remaining -= file.size
        toc_str += "\n│"
        toc_str += "\n└ \x1b[93m" + str(_remaining) + "\x1b[0m Remaining"
        return toc_str
    
    def getAsJson(self) -> json:
        """
        Returns the data of the TableOfContent object as a JSON string.
        """
        if (self.files[0].cksum.value != "00000000000000000000000000000000"):
            # If Checksum…
            toc_dict = {
                "toc": {
                    "files": [
                        {
                            "id": file.id,
                            "name": file.name,
                            "path": file.path,
                            "size": file.size,
                            "cksum": {
                                "type": file.cksum.type,
                                "value": file.cksum.value
                            }
                        }
                        for file in self.files
                    ],
                    "ltoV": self.ltoV,
                    "bs": self.bs,
                    "tape_size": self.tape_size,
                    "tbkV": self.tbkV,
                    "last_mod": self.last_mod
                }
            }
        else:
            toc_dict = {
                "toc": {
                    "files": [
                        {
                            "id": file.id,
                            "name": file.name,
                            "path": file.path,
                            "size": file.size,
                        }
                        for file in self.files
                    ],
                    "ltoV": self.ltoV,
                    "bs": self.bs,
                    "tape_size": self.tape_size,
                    "tbkV": self.tbkV,
                    "last_mod": self.last_mod
                }
            }
        return toc_dict
    
    def from_createJob(self, blockSize: str, directory: str, ltoV: int) -> json: #TODO
        
        self.bs = blockSize
        self.ltoV = ltoV
        
        
        return self.getAsJson(self)
    
    def from_json(self, json_data: dict) -> bool:
        try:
            self.files = [
                File(
                    id=file["id"],
                    name=file["name"],
                    path=file["path"],
                    size=file["size"]
                )
                for file in json_data["files"]
            ]
            self.ltoV = json_data["ltoV"]
            self.bs = json_data["bs"]
            self.tape_size = json_data["tape_size"]
            self.tbkV = json_data["tbkV"]
            self.last_mod = json_data["last_mod"]
            return True
        except KeyError as e:
            if DEBUG: print(f"[ERROR] Missing required field in JSON: {e}")
            return False
        except Exception as e:
            if DEBUG: print(f"[ERROR] Could not parse Table of Contents: {e}")
            return False
    
    def create(self, target_dir: str, blocksize: str, ltoVersion: int , cksum: bool = True) -> None:
        if not self.getFilesFromDir(directory=target_dir):
            return None
        self.ltoV = ltoVersion
        self.bs = blocksize
        self.tape_size = self.get_tape_size_from_json()
        self.tbkV = VERSION
        self.last_mod = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        
        return self
    
    def getFilesFromDir(self, directory: str) -> bool: 
        # does modify self.files, so it'll return success or failure
        try:
            for index, path in enumerate(os.listdir(path=directory)):
                full_path: str = directory + "/" + path
                self.files.append(File(id=index,
                            size=os.path.getsize(full_path),
                            name=path,
                            path=full_path
                            ))
            return True
        except:
            return False
    
    def __str__(self) -> str:
        return str(self.showTOC()  + "\n")

import json
import os
import xml.etree.ElementTree as ET
from tbk.File import File

DEBUG: bool = True
VERSION: str = "4.0.0"

class TableOfContent:

    files: list[File]
    ltoV : int
    bs: str
    tape_size : int
    tbkV : str
    last_mod : str

    def __init__(self, files: list[File], lto_version: str, optimal_blocksize: str, tbk_version: str = VERSION, last_modified: str = "") -> None:
        
        if files is []: return
        self.files: list[File] = files      # List of all Files from TableOfContent
        self.ltoV: int = lto_version  # LTO-Version of Tape/Drive
        self.bs: str = optimal_blocksize    # Optimal Blocksize
        self.tape_size: int = self.get_tape_size_from_json()    # Constant, depends on LTO-Version TODO!
        self.tbkV: str = tbk_version        # Software-Version of Tape-Backup-Software from original TOC
        self.last_mod: str = last_modified  # Optional Timestamp (required for reading of tape)
        
        
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
                                size=int(str(xml_root[index][3].text)),
                                cksum_type=str(xml_root[index][4].text),
                                cksum=str(xml_root[index][5].text)
                ))
            except:
                self.files.append(File(id=int(str(xml_root[index][0].text)),
                                name=str(xml_root[index][1].text),
                                path=str(xml_root[index][2].text),
                                size=int(str(xml_root[index][3].text))
                ))
        
        self.ltoV = int(xml_root[0][0].text)
        self.bs = str(xml_root[0][1].text)
        self.tape_size = self.get_tape_size_from_json()
        self.tbkV = str(xml_root[0][3].text)
        self.last_mod = str(xml_root[0][4].text)
    
        return "Success"

    def get_tape_size_from_json(self) -> int:
        script_dir = os.path.dirname(__file__)  # Get the directory of the current script
        json_path = os.path.join(script_dir, 'rbs_ltoV.json')  # Construct the relative path
        with open(json_path, 'r') as f:
            lto_data = json.load(f)
            for lto in lto_data["LTO_Standards"]:
                if lto["Generation"] == self.ltoV:
                    return lto["capacityInBytes"]
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
            toc_str += "\n│ ├── Size:\t" + str(file.size)
            toc_str += "\n│ └── Checksum:\t" + file.cksum
            toc_str += "\n│"
            _remaining -= file.size
        toc_str += "\n│"
        toc_str += "\n└ \x1b[93m" + str(_remaining) + "\x1b[0m Remaining"
        return toc_str
    
    def getAsJson(self) -> json:
        """
        Gibt die Daten des TableOfContent-Objekts als JSON-String zurück.
        """
        toc_dict = {
            "toc": {
                "files": [
                    {
                        "id": file.id,
                        "name": file.name,
                        "path": file.path,
                        "size": file.size,
                        "cksum": file.cksum,
                        "cksum_type": file.cksum_type
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
    
    def from_createJob(self, blockSize: str, directory: str, ltoV: int) -> json:
        
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
        return self.showTOC()

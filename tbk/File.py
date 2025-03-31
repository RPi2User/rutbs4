import subprocess

DEBUG: bool = True

class File:

    id: int
    size : int
    name : str                  # Just name with extension
    path : str                  # Complete-path including filename!
    cksum : str
    cksum_type : str = "md5"    # "Constant" (currently, SHA256 is waaay to slow)
    
    

    def __init__(self, id: int, name: str, path: str, size: int = 0, cksum: str = "00000000000000000000000000000000", cksum_type: str = "") -> None:
        self.id: int = id
        self.size: int = size
        self.name: str = name
        self.path: str = path
        self.cksum: str = cksum
        self.cksum_type: str = cksum_type
        
    def CreateChecksum(self) -> None:
        # Some bash/awk/string-Magic to get checksum from "md5sum" command
        if DEBUG: print("Creating checksum for " + str(self))
        _out: str = str(subprocess.check_output("md5sum '" + self.path +  "' | awk '{ print $1}'", shell=True))
        _out = _out.split("'", 2)[1].split("\\", 1)[0]
        self.cksum = _out
    
    def CheckFileIntegrety(self) -> bool:
        return False
    
    def __str__(self) -> str:
        return "File(ID: " + str(self.id) + ", Size: " + str(self.size) + ", Name: " + self.name + ", Path: " + self.path + ", cksum: " + self.cksum + ", cksum_type: " + self.cksum_type + ")"
    
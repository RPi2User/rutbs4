import subprocess

from tbk.Checksum import Checksum

DEBUG: bool = True

class File:

    id: int
    size : int
    name : str                  # Just name with extension
    path : str                  # Complete-path including filename!
    cksum : Checksum
    
    

    def __init__(self, id: int, name: str, path: str, cksum: Checksum = Checksum(), size: int = 0) -> None:
        self.id: int = id
        self.size: int = size
        self.name: str = name
        self.path: str = path
        self.cksum: Checksum = Checksum(cksum.value, cksum.type)
        
    def CreateChecksum(self, readWrite: bool) -> bool: # rw: true READ, false WRITE
        # Some bash/awk/string-Magic to get checksum from "md5sum" command
        _out: str = str(subprocess.check_output("md5sum '" + self.path +  "' | awk '{ print $1}'", shell=True))
        _out = _out.split("'", 2)[1].split("\\", 1)[0]
        if DEBUG: print("[INFO] Checksum for " + str(self) + ": " + _out)
        if self.cksum.value != _out and readWrite:
            print("[ERROR] Checksum MISMATCH for " + str(self) + " IS LOCAL " + _out)
            return False
        else:
            self.cksum.value = _out
            self.cksum.type = "md5"
            return True
    
    def __str__(self) -> str:
        return "File(ID: " + str(self.id) + ", Size: " + str(self.size) + ", Name: " + self.name + ", Path: " + self.path + ", cksum: " + str(self.cksum) + ")"
    
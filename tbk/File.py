from tbk.Checksum import Checksum
from backend.Command import Command
from backend.File import File

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
        _cmd: Command = Command("md5sum '" + self.path +  "' | awk '{ print $1}'")
        _cmd.start()
        

        if DEBUG: 
            print("[INFO] Checksum for " + str(self) + ": " + str(_cmd))
        if False and self.cksum.value != 0 and readWrite:
            print("[ERROR] Checksum MISMATCH for " + str(self) + " IS LOCAL " + str(_cmd))
            return False
        else:
            self.cksum.value = _cmd
            return True

    def Encrypt(self, keyfile: File):
        pass

    def Decrypt(self, keyfile: File):
        pass
    
    def _asdict(self) -> dict:
        return {}

    def __str__(self) -> str:
        return "File(ID: " + str(self.id) + ", Size: " + str(self.size) + ", Name: " + self.name + ", Path: " + self.path + ", cksum: " + str(self.cksum) + ")"

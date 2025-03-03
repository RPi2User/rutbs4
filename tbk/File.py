import subprocess

class File:

    id: int
    size : int
    name : str
    path : str
    cksum : str
    cksum_type : str = "MD5"    # "Constant" (currently, SHA256 is waaay to slow)
    
    

    def __init__(self, id: int, size: int, name: str, path: str, cksum: str = "") -> None:
        self.id: int = id
        self.size: int = size
        self.name: str = name
        self.path: str = path
        self.cksum: str = cksum
        
    def CreateChecksum(self) -> None:
        # Some bash/awk/string-Magic to get checksum from "md5sum" command
        _out: str = str(subprocess.check_output("md5sum '" + self.path + "/" + self.name + "' | awk '{ print $1}'", shell=True))
        _out = _out.split("'", 2)[1].split("\\", 1)[0]
        self.cksum = _out
    
    def __str__(self) -> str:
        return "File(ID: " + str(self.id) + ", Size: " + str(self.size) + ", Name: " + self.name + ", Path: " + self.path + ", cksum: " + self.cksum + ", cksum_type: " + self.cksum_type + ")\n"
    
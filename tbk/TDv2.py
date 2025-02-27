import os
from tbk import TableOfContent
import tbk.File as File

class TapeDrive:
    
    path : str
    ltoVersion : int
    status : int
    blockSize : str
    
    
    def __init__(self, path_to_tape_drive: str, blockSize: str = "1M" ) -> None:
        self.blockSize: str = blockSize
        self.path: str = path_to_tape_drive
        
        
    def write(self, file: File) -> None:
        
        _ec = os.system("dd if='" + file.path + "' of="+ self.path + " bs=" + self.blockSize + " 2>/dev/null")
        _ec = os.system("dd if='" + file.path + "' of="+ self.path + " bs=" + self.blockSize + " status=progress")
    
    
    def read(self, file: File) -> None:
        pass
    
    def calcChecksum(self, file: File) -> None:
        pass
    
    def readTOC() -> TableOfContent:
        pass
    
    def writeTOC(toc : TableOfContent) -> None:
        pass
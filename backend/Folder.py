import json
from enum import Enum
from typing import List

from backend.Encryption import E_Mode
from backend.File import File
from backend.Command import Command
from backend.Checksum import ChecksumType

class Folder:


    def __init__(self, path: str, checksumType: ChecksumType, encryptionMode: E_Mode = E_Mode.NONE):
        self.files: List[File] = []
        self.path: str = ""
        self.encMode: E_Mode = encryptionMode
        self.path = path
        _find_cmd: str = "find '" + path + "' -maxdepth 1 -type f"
        _id = 0
        find_files: Command = Command(_find_cmd)
        find_files.wait()   # wait until the find process is finished, shall be instant
        for file in find_files.stdout:
            pass
            #self.files.append(file)

    def encrypt(self):
        pass

    def decrypt(self):
        pass

    # SYSTEM
    def __str__(self) -> str:
        return json.dumps(self._asdict())
    
    def _asdict(self) -> dict:
        data = {
            "path": self.path,
            "encryption_type": self.encMode.name,
            "files" : [file._asdict() for file in self.files]
        }
        return data
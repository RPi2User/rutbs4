import json
from enum import Enum
from typing import List
from backend.File import File
from backend.Command import Command
from backend.Checksum import ChecksumType

class FolderKeyType(Enum):
    FILE = 1
    PASSPHRASE = 2
    NO_ENCRYPTION = 3

class Folder:

    def setChecksumType(self, cksumType: ChecksumType) -> None:
        self.cksumType = cksumType

    def encryptByPassphrase(self, passphrase: str):
        pass

    def encryptByKeyfile(self, keyfile: File):
        pass

    def decryptByPassphrase(self, passphrase: str):
        pass

    def decryptByKeyfile(self, keyfile: File):
        pass

    def __init__(self, path: str):
        self.files: List[File] = []
        self.path: str = ""
        self.encyrption_status: FolderKeyType = FolderKeyType.NO_ENCRYPTION
        self.path = path
        _find_cmd: str = "find '" + path + "' -maxdepth 1 -type f"
        _id = 0
        find_files: Command = Command(_find_cmd)
        find_files.wait()   # wait until the find process is finished, shall be instant
        for file in find_files.stdout:
            self.files.append(File(
                id = _id,
                path = file))
            _id+=1

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
            "encryption_state": self.encyrption_status.name,
            "files" : [file._asdict() for file in self.files]
        }
        return data
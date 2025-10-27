import json
from typing import List
from backend.File import File
from backend.Command import Command


class Folder:

    FILE: int = 1
    PASSPHRASE: int = 2
    NO_ENCRYPTION: int = 0

    files: List[File] = []
    path: str = ""
    encyrption_status: int = NO_ENCRYPTION

    def encryptByPassphrase(self, passphrase: str):
        pass

    def encryptByKeyfile(self, keyfile: File):
        pass

    def decryptByPassphrase(self, passphrase: str):
        pass

    def decryptByKeyfile(self, keyfile: File):
        pass

    def __init__(self, path: str):
        self.path = path
        _find_cmd: str = "find '" + path + "' -maxdepth 1 -type f"
        _id = 0
        find_files: Command = Command(_find_cmd)
        find_files.start()
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
            "encryption_state": self.encyrption_status,
            "files" : [file._asdict() for file in self.files]
        }
        return data
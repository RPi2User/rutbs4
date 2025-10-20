import json
from typing import List
from backend.File import File
from backend.Command import Command


class Folder:
    
    files: List[File] = []
    path: str = ""

    def encrypt(self, keyfile: File):
        pass

    def decrypt(self, keyfile: File):
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
                name =  file.split('/')[-1],
                path = file))
            _id+=1

    def __str__(self) -> str:
        return json.dumps(self._asdict())
    
    def _asdict(self) -> dict:
        data = {
            "path": self.path,
            "files" : [file._asdict() for file in self.files]
        }
        return data
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
    
    # This generates a List 
    def __init__(self, path: str):
        _find_cmd: str = "find '" + path + "' -maxdepth 1 -type f"
        _id = 0
        find_files: Command = Command(_find_cmd)
        find_files.start()
        for file in find_files.stdout:
            self.files.append(File(
                id = _id,
                name =  file.split('/')[-1],
                path = file))
            print(self.files[_id])
            _id+=1

    def __str__(self) -> str:
        return json.dumps(self._asdict())
    
    def _asdict(self) -> dict:
        data = {
            "files" : self.files,
            "path": self.path
        }
        
        return data
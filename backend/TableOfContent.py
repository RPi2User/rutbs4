import json

from typing import List

from backend.Command import Command
from backend.Folder import Folder

class TableOfContent:

    command = None
    rootFolder: Folder
    folder: List[Folder] = []

    def _scanSubDirs(self):
        # -mindepth 1 is used so the root dir is not element of folder{}
        self.command = Command("find '" + self.rootFolder.path + "' -mindepth 1 -maxdepth 1 -type d")
        self.command.wait()
        for folder in self.command.stdout:
            self.folder.append(Folder(folder.split('/')[-1]))   # Get substring after last slash

    def __init__(self, rootFolder: Folder) -> None:
        # 1. Add all Folders to list
        # 2. Add all Files from Root Folder
        self.rootFolder = rootFolder
        self._scanSubDirs() # When no subdirs available, find returns nothing with exit_code = 0
    
    
    def _asdict(self) -> dict:
        data = {
            "rootFolder": self.rootFolder._asdict(),
            "folders": [folder._asdict() for folder in self.folder],
        }
        
        return data
    
    def __str__(self) -> str:
        return json.dumps(self._asdict())
    
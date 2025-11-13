import json
import platform

from datetime.datetime import datetime
from typing import List

from backend.TapeDrive import TapeDrive

from backend.Command import Command
from backend.Folder import Folder

"""_summary_
    Host must create a suitable TOC, with a valid TapeDrive object.
    After that, the TOC must be passed to the Read/Write-Scheduler
"""

class TOC_System:

    timeStamp: str = ""
    hostname: str = ""
    threadCount: int = 0
    tapeDrive: dict = {}


    def __init__(self, tapeDrive: TapeDrive, threadCount: int):
        self.timeStamp = datetime.now()
        self.hostname = platform.node()
        self.threadCount = threadCount
        self.tapeDrive = tapeDrive._asdict()


    def _asdict(self)-> dict:
        data = {
            "timeStamp": self.timeStamp,
            "hostname": self.hostname,
            "threadCount": self.threadCount,
            "tapeDrive": self.tapeDrive,
        }
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict())


class TableOfContent:

    """_summary_
        A TableOfContent contains the following groups:
        - System Data
        - Job Properties
        - All (future) FILES written on the Tape

        NOTE: Tape Properties are included in TapeDrive object!

        System Data:
        - TimeStamp
        - Hostname
        - Thread Count
        - TapeDrive

        Job Properties:
        - Encryption Scheme
        - Checksum Type

        Folder:
        - rootFolder
        - folder[]
    """


    def _scanSubDirs(self):
        # -mindepth 1 is used so the root dir is not element of folder{}
        self.command = Command("find '" + self.rootFolder.path + "' -mindepth 1 -maxdepth 1 -type d")
        self.command.wait()
        for folder in self.command.stdout:
            self.folder.append(Folder(folder))

    def __init__(self, rootFolder: Folder) -> None:
        self.command = None
        self.rootFolder: Folder
        self.folder: List[Folder] = []
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
    
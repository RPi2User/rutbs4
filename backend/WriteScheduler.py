import json

from typing import List
from enum import Enum

from backend.Command import Command
from backend.TapeDrive import TapeDrive
from backend.File import File
from backend.Folder import Folder
from backend.Checksum import Checksum, ChecksumType

class WS_States(Enum):
    WAIT_FOR_DRIVE = 0
    WAIT_FOR_CHECKSUM = 1
    ERROR = 2

class WriteScheduler():

    # --- Vars -----------------------------------------------------
    state: WS_States = WS_States.ERROR
    drive: TapeDrive
    threadLimit: int
    cksum_type: ChecksumType
    folders: List[Folder] = []
    writePipeline: List[File] = []
    cksumPipeline: List[File] = []

    def _initPipelines(self) -> None:
        pass

    def work(self):
        pass

    # --- System ---------------------------------------------------
    def __init__(self, tapeDrive: TapeDrive, targetFolders: List[Folder], threadLimit: int, cksum_type: ChecksumType = ChecksumType.NONE) -> None:
        self.drive = tapeDrive
        self.folders = targetFolders
        if (threadLimit < 1):
            self.threadLimit = 1
        else:
            self.threadLimit = threadLimit
        self.cksum_type = cksum_type

    def _asdict(self) -> dict:
        data =  {
            "issue", self.state.name,
            "drive", self.drive._asdict(),
            "folders", [folder._asdict() for folder in self.folders],
            "writePipeline", [file._asdict() for file in self.writePipeline],
            "cksumPipeline", [file._asdict() for file in self.cksumPipeline],
        }
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict())
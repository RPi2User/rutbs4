import json
import tbk.TableOfContent as TableOfContent
import backend.File as File
import backend.Command as Command

from tbk.TapeDriveCommands import TapeDriveCommands as TDC
from tbk.Status import Status

DEBUG: bool = False
VERSION = 4.1


# lets boot that file up again

class TapeDrive:

    _status: Status = Status.ERROR
    path: str = ""
    generic_path: str = ""
    _blocksize: str = ""
    _command: Command
    _readOnly:  bool = True
    file: File

    def __init__(self, path: str, generic_path: str):
        self.path = path
        self.generic_path = generic_path

    def _asdict(self) -> dict:
        data = {
            "path": self.path,
            "generic_path": self.generic_path,
            # TODO: current operation
            "currentFile": self.file,
        }
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict())

    def getStatus(self) -> Status:
        pass

    def rewind(self):
        if self._status != Status.NOT_AT_BOT:
            return

        self._status = Status.REWINDING
        self.__rewind()
        
        if self._readOnly:    
            self._status = Status.TAPE_RDY_WP
        else:
            self._status = Status.TAPE_RDY


    def eject(self):
        if self._status != {Status.NOT_AT_BOT, Status.TAPE_RDY, Status.TAPE_RDY_WP}:
            return
        self._status = Status.EJECTING

        # After Success, set current State accordingly
        self._status = Status.NO_TAPE


    def write(self, file: File):
        if self._status != {Status.NOT_AT_BOT, Status.TAPE_RDY}:
            return
        self._status = Status.WRITING

        # After Success, set current State accordingly
        self._status = Status.NOT_AT_BOT

    def writeTOC(self, tableOfContent: TableOfContent):
        # This writes TOC as first File on Tape
        pass
        

    def read(self, f: File):
        self._status = Status.READING
        self._status = Status.NOT_AT_BOT

    def __rewind(self):
        c: Command = TapeDrive.COMMANDS[TapeDrive.REWIND]
        c.start()

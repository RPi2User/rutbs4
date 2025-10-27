import json

from enum import Enum
from backend.Command import Command

class ChecksumType(Enum):
    MD5 = 1
    SHA256 = 2

class Checksum:

    type: ChecksumType = ChecksumType.MD5
    file_path: str = ""
    value: str = ""
    cmd: Command = Command("")

    def __init__(self, file_path: str, type: int = ChecksumType.MD5):
        self.type = type
        self.file_path = file_path

    def create(self):
        if (self.type == ChecksumType.MD5):
            self.cmd = Command("openssl md5 -r '" + self.file_path +"'")
        else:
            self.cmd = Command("openssl sha256 -r '" + self.file_path + "'")
        self.cmd.start()
    
    def _status(self) -> None:
        if self.cmd.running:
            return
        if self.cmd.exitCode == 0:
            self.value = self.cmd.stdout[0].split()[0]
        else:
            pass 
        # Why don't we eval this error State?
        # This class has no messaging capabilities.
        # Caller needs to implement error handling.

    def _asdict(self) -> dict:
        self._status()
        data = {
            "type" : self.type.name,
            "value" : self.value,
            "command": self.cmd._asdict()
        }
        return data

    def __str__(self):
        return json.dumps(self._asdict())
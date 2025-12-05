import json

from enum import Enum
from backend.Command import Command

class ChecksumType(Enum):
    MD5 = 1
    SHA256 = 2
    NONE = 3

class Checksum:

    def __init__(self, file_path: str, type: ChecksumType = ChecksumType.MD5):
        self.type: ChecksumType = ChecksumType.MD5
        self.file_path: str = ""
        self.value: str = None
        self.cmd: Command = Command("")
        self.type = type
        self.file_path = file_path
        self.mismatch: bool = True
        self.old_value: str = "CKSUM_OKAY"

    def create(self):
        if (self.type == ChecksumType.NONE):
            return  # Do nothing when user wants nothing.
        if (self.type == ChecksumType.MD5):
            self.cmd = Command("openssl md5 -r '" + self.file_path +"'")
        else:
            self.cmd = Command("openssl sha256 -r '" + self.file_path + "'")
        self.cmd.start()
    
    def _status(self) -> None:
        self.cmd.status()
        if self.cmd.running:
            return
        if self.cmd.exitCode == 0:
            new_value = self.cmd.stdout[0].split()[0]

            if self.value is None:
                # we are creating a checksum, not validating...
                self.value = new_value
                self.mismatch = False
                self.old_value = "CKSUM_CREATED"

            if self.value != new_value:
                # checksum mismatch
                self.mismatch = True

            if self.value == new_value:
                # checksum validated
                self.mismatch = False

            self.old_value = self.value
            self.value = new_value

        else:
            pass 


        # Why don't we eval self.cmd.exitcode != 0?
        # This class has no messaging capabilities.
        # Caller needs to implement error handling (e.g. mismatches).

    def _asdict(self) -> dict:
        self._status()
        summary = {
            "mismatch": self.mismatch,
            "old_value": self.old_value
        }
        data = {
            "type" : self.type.name,
            "value" : self.value,
            "summary": summary,
            "command": self.cmd._asdict()
        }
        return data

    def __str__(self):
        return json.dumps(self._asdict())

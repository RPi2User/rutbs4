import json

from enum import Enum
from backend.Command import Command

class ChecksumState(Enum):
    CREATE = 1,
    VALIDATING = 2,
    IDLE = 3,
    ERROR = 4,
    MISMATCH = 5

class ChecksumType(Enum):
    MD5 = 1
    SHA256 = 2
    NONE = 3

class Checksum:

    # TODO: 1. checksum.wait()
    #       2. checksum.check(target: str)

    def __init__(self, file_path: str, type: ChecksumType = ChecksumType.SHA256):
        self.state : ChecksumState = ChecksumState.IDLE
        self.type: ChecksumType = type
        self.file_path: str = ""
        self.value: str = ""
        self.cmd: Command = Command("")
        self.type = type
        self.file_path = file_path
        self.mismatch: bool = True
        self.old_value: str = "CKSUM_OKAY"

    def create(self):
        if self.state != ChecksumState.IDLE or self.type == ChecksumType.NONE:
            return

        match self.type:
            case ChecksumType.MD5:
                self.cmd = Command("openssl md5 -r '" + self.file_path +"'")

            case ChecksumType.SHA256:
                self.cmd = Command("openssl sha256 -r '" + self.file_path +"'")

        self.cmd.start()
    
    def _status(self) -> None:
        self.cmd.status()
        if self.cmd.running:
            return
        if (self.cmd.exitCode == 0) and not (self.old_value == "CKSUM_CREATED"):    # this "and not" reduces multiple 
            new_value = self.cmd.stdout[0].split()[0]

            if (self.value == ""):
                # we are creating a checksum, not validating...
                self.value = new_value
                self.mismatch = False
                self.old_value = "CKSUM_CREATED"
                return  # so our "message" won't get overwritten

            if self.value != new_value:
                # checksum mismatch
                self.mismatch = True
                self.old_value = self.value

            if self.value == new_value:
                # checksum validated
                self.mismatch = False

            self.value = new_value

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

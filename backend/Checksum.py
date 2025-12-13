import json

from enum import Enum
from backend.Command import Command

class ChecksumState(Enum):
    CREATE = 1,     # when a new checksum shall be calculated
    VALIDATE = 2,   # when cross-checking the file integrity
    IDLE = 3,       # when ALL_OKAY
    ERROR = 4,      # when Checksum.cmd.exitCode != 0
    MISMATCH = 5    # when VALIDATING -> IDLE (but with cksum_old != cksum_current)

class ChecksumType(Enum):
    MD5 = 1
    SHA256 = 2
    NONE = 3

class Checksum:

    # TODO: 1. checksum.wait()
    #       2. checksum.check(target: str)

    def __init__(self, file_path: str, type: ChecksumType = ChecksumType.SHA256):
        self.type: ChecksumType = type
        self.file_path: str = ""
        self.value: str = ""
        self.cmd: Command = Command("")
        self.type = type
        self.file_path = file_path
        self.validation_target: str = ""
        self.state : ChecksumState = ChecksumState.IDLE

    def create(self):
        if self.state != ChecksumState.IDLE or self.type == ChecksumType.NONE:
            return

        match self.type:
            case ChecksumType.MD5:
                self.cmd = Command("openssl md5 -r '" + self.file_path +"'")

            case ChecksumType.SHA256:
                self.cmd = Command("openssl sha256 -r '" + self.file_path +"'")

        self.state = ChecksumState.CREATE
        self.cmd.start()

    def validate(self, target: str) -> None:
        if self.state != ChecksumState.IDLE:
            return

        if len(target) == 0:
            raise SystemError("[ERROR] Checksum validation: Target checksum empty!")

        self.state = ChecksumState.VALIDATE
        self.validation_target = target
        self.create()
        self._status()

    def wait(self) -> None:
        self.cmd.wait()
        self._status()

    def _status(self) -> None:
        self.cmd.status()   # refresh current state

        if self.cmd.running:    # abort if running
            return

        if self.cmd.exitCode != 0:  # Annoy user if error occured, be eff. write-protect
            self.state = ChecksumState.ERROR
            return

        match self.state:
            case ChecksumState.IDLE:
                    return # we don't care, cmd exited fine (!= 0)
            case ChecksumState.CREATE:
                self._fin_create()
            case ChecksumState.VALIDATE:
                self._fin_validate()

    def _fin_create(self) -> None:
        self.value = self.cmd.stdout[0].split()[0]
        self.state = ChecksumState.IDLE

    def _fin_validate(self) -> None:
        self.value = self.cmd.stdout[0].split()[0]

        if self.value != self.validation_target:
            self.state = ChecksumState.MISMATCH
        else:
            self.state = ChecksumState.IDLE

    def _asdict(self) -> dict:
        self._status()
        data = {
            "type" : self.type.name,
            "state" : self.state.name,
            "value" : self.value,
        }

        if len(self.validation_target) != 0: # add target value if necessary
            data.update({"target_value": self.validation_target}) 

        data.update({"command": self.cmd._asdict()})
        return data

    def __str__(self):
        return json.dumps(self._asdict())

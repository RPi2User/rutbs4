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
    SHA512 = 3 # TODO Unit_Test!
    NONE = 99

class Checksum:

    """
    #### === CHECKSUM =========================================================

    Checksum.__init__(file_path: str, type: ChecksumType = ChecksumType.SHA256, value: str = "", target_value: str = ""):
    - Requires
        - file_path like "./foo/bar/baz/mreow.txt" OR "/opt/env/secret.txt"
    - Accepts:
        - Custom Checksum Type: 
            - ChecksumType.SHA256
            - ChecksumType.SHA512
            - ChecksumType.MD5
            - ChecksumType.NONE
        - value: UNSAFE predefine value (useful to restore a known checksum)
        - target_value: Target value (needed for file validation)

    #### --- EXCEPTIONS -------------------------------------------------------

    **SystemError**:  
    Checksum validation. Raises a SystemError when target checksum value is empty.
    """

    def __init__(self, file_path: str, type: ChecksumType = ChecksumType.SHA256, value: str = "", target_value: str = ""): # BUG If init with sha256 cant change to md5
        self.file_path: str = file_path
        self.value: str = value
        self.validation_target: str = target_value

        # Set type and finish init.
        self.setType(type)
        self.state : ChecksumState = ChecksumState.IDLE

    # --- PUBLIC FUNCTIONS ----------------------------------------------------

    def setType(self, target_type: ChecksumType) -> None:
        self.type = target_type
        if not hasattr(self, "cmd"):
            self.cmd: Command = Command("openssl " + self.type.name.lower() + " -r '" + self.file_path + "'")
            return
        self.cmd.cmd = "openssl " + self.type.name.lower() + " -r '" + self.file_path + "'"

    def create(self):
        if self.state != ChecksumState.IDLE or self.type == ChecksumType.NONE:
            return

        self.state = ChecksumState.CREATE
        self.cmd.start()

    def validate(self, target: str) -> None:
        if self.state != ChecksumState.IDLE:
            return

        if len(target) == 0:
            raise SystemError("[ERROR] Checksum validation: Target checksum empty!")

        self.validation_target = target
        self.create()

        self.state = ChecksumState.VALIDATE
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
                    return # we don't care, cmd exited fine ($? != 0)
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

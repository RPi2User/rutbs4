import json
import re
from enum import Enum

from backend.Command import Command
from backend.Job import Job

class KeyLength(Enum):
    # aes does not allow larger keys
    short = 16     # 16 byte -> 128 Bit
    medium = 32    # 32 byte -> 256 Bit

class Key:

    def __init__(self, length: KeyLength = KeyLength.medium, value: str = "", iv: str = "", empty: bool = False):
        """
        Without `value` and `iv` a new random pair is made. With them it is a key read back from a TOC.
        `empty=True` is no key at all, for files that are not encrypted.
        """
        self.length: KeyLength = length

        if empty:
            self.cmd = Command("")
            self.value: str = ""
            self.iv: str = ""
            return

        if value:
            self.cmd = Command("")      # nothing was run, the pair comes from the TOC
            self.value: str = value
            self.iv: str = iv
            # It comes from a tape and ends up in a command: nothing but hex digits is accepted
            if not self._isHex(self.value, self.length.value) or not self._isHex(self.iv, 16):
                raise ValueError("[ERROR] Key or IV from the TOC is not valid")
            return

        # Generate Key
        self.cmd = Job.Run(Command("openssl rand " + str(length.value), raw=True))
        self.value = self.cmd.stdout[0] if self.cmd.stdout else ""

        if len(self.value) != self.length.value * 2:
            self.iv = "CRASHED"
            print(self)
            raise SystemError("[ERROR] Keylength wrong, check logs!")

        # Generate Init. Vektor
        self.cmd = Job.Run(Command("openssl rand 16", raw=True))
        self.iv = self.cmd.stdout[0] if self.cmd.stdout else "CRASHED"
        if not self._isHex(self.iv, 16):
            raise SystemError("[ERROR] No IV, check logs!")

    @staticmethod
    def _isHex(text: str, size: int) -> bool:
        "`size` bytes as hex digits"
        return isinstance(text, str) and re.fullmatch(r"[0-9a-fA-F]{" + str(size * 2) + "}", text) is not None

    def _asdict(self) -> dict:
        data = {
            "length": self.length.name,
            "value": self.value,
            "iv": self.iv,
            "cmd": self.cmd._asdict()
        }
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

class E_State(Enum):
    IDLE = 0,
    ENCRYPT = 1,
    DECRYPT = 2,
    ERROR = 3

class E_Mode(Enum):
    NONE = 0        # nothing is encrypted, encrypt() and decrypt() do nothing
    AES128CBC = 1
    AES256CBC = 2
    AES128CTR = 3
    AES256CTR = 4

class Encryption:

    KEY_ENV: str = "RUTBS_KEY"  # openssl reads the key from the environment, so it is not visible in `ps`

    MODE_CMD = {
        E_Mode.AES128CBC: "openssl aes-128-cbc -pbkdf2 ",
        E_Mode.AES256CBC: "openssl aes-256-cbc -pbkdf2 ",
        E_Mode.AES128CTR: "openssl aes-128-ctr -pbkdf2 ",
        E_Mode.AES256CTR: "openssl aes-256-ctr -pbkdf2 ",
    }

    def __init__(self, key: Key, mode: E_Mode = E_Mode.AES256CBC):
        self.key = key
        self.mode = mode
        self.cmd = Command("")
        self.state: E_State = E_State.IDLE
        self.targetPath = ""

    def refresh(self) -> None:
        self.cmd.status()

        if self.cmd.running:    # do nothing if status still same
            return

        if not self.cmd.didRun:    # not started yet (e.g. queued for the Job scheduler)
            return

        if self.state in [E_State.ENCRYPT, E_State.DECRYPT ]:
            if self.cmd.exitCode != 0:
                self.state = E_State.ERROR
            else:
                self.state = E_State.IDLE

        # Continue IDLEing

    def decrypt(self, path: str, target: str = "") -> None:
        if self.state != E_State.IDLE or self.mode == E_Mode.NONE:
            return

        self.state = E_State.DECRYPT

        self.targetPath = target or ".".join([part for part in path.split('.')[:-1]]) # default: removes ".tail"

        # A new Command every time: the Job queue keeps finished Commands and refuses a second Add() of the same object
        self.cmd = Command(self.MODE_CMD[self.mode] + "-d -iv " + Command.quote(self.key.iv) + " -pass env:" + self.KEY_ENV +
                           " -in " + Command.quote(path) + " -out " + Command.quote(self.targetPath),
                           env={self.KEY_ENV: self.key.value})

    def encrypt(self, path: str, target: str = "") -> None:
        if self.state != E_State.IDLE or self.mode == E_Mode.NONE:
            return

        self.state = E_State.ENCRYPT

        self.targetPath = target or path + ".crypt"   # target: e.g. a file in the spool

        self.cmd = Command(self.MODE_CMD[self.mode] + "-e -iv " + Command.quote(self.key.iv) + " -pass env:" + self.KEY_ENV +
                           " -in " + Command.quote(path) + " -out " + Command.quote(self.targetPath),
                           env={self.KEY_ENV: self.key.value})

    def _asdict(self) -> dict:
        self.refresh()
        data = {
            "state": self.state.name,
            "mode": self.mode.name,
            "newFilePath": self.targetPath,
            "key": self.key._asdict(),
            "cmd": self.cmd._asdict()
        }
        return data
    
    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

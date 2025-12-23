import json
from typing import List
from enum import Enum

from backend.Command import Command

class KeyLength(Enum):
    # aes does not allow larger keys
    short = 16     # 16 byte -> 128 Bit
    medium = 32    # 32 byte -> 256 Bit

class Key:

    def __init__(self, length: KeyLength = KeyLength.medium):
        self.cmd = Command("openssl rand " + str(length.value), raw=True)
        self.cmd.wait()
        self.length: KeyLength = length
        self.value: str = self.cmd.stdout[0]

    def _asdict(self) -> dict:
        if len(self.value) != 0:
            value_exist: str = "<redacted>"
        data = {
            "length": self.length.name,
            "value": value_exist
        }
        return data

class E_State(Enum):
    IDLE = 0,
    ENCRYPT = 1,
    DECRYPT = 2,
    ERROR = 3

class E_Mode(Enum):
    AES128CBC = 1
    AES256CBC = 2
    AES128CTR = 3
    AES256CTR = 4

class Encryption:
    
    MODE_CMD = {
        E_Mode.AES128CBC: "openssl aes-128-cbc -pbkdf2 ",
        E_Mode.AES256CBC: "openssl aes-256-cbc -pbkdf2 ",
        E_Mode.AES128CTR: "openssl aes-128-ctr -pbkdf2 ",
        E_Mode.AES256CTR: "openssl aes-256-ctr -pbkdf2 ",
    }

    def __init__(self, key: Key, mode: E_Mode = E_Mode.AES256CBC):
        self.key = key
        self.mode = mode
        self.cmd = Command("openssl rand -hex 16")
        self.cmd.wait()
        self.iv: str = self.cmd.stdout[0]
        self.state: E_State = E_State.IDLE
        
    def refresh(self) -> None:
        self.cmd.status()

        if self.cmd.running:    # do nothing if status still same
            return

        if self.state in [E_State.ENCRYPT, E_State.DECRYPT ] :
            if self.cmd.exitCode != 0:
                self.state = E_State.ERROR
            else:
                self.state = E_State.IDLE

        # Continue IDLEing

    def decrypt(self, path: str) -> str:
        if self.state != E_State.IDLE:
            return path # DO NOTHING

        self.state = E_State.ENCRYPT

        fin_path = ".".join([part for part in path.split('.')[:-1]]) # removes ".tail"
        self.cmd.cmd = self.MODE_CMD[self.mode] + "-d -iv " + self.iv + " -k " + self.key.value + " -in '" + path + "' -out '" + fin_path + "'"
        self.cmd.start()

        self.refresh()
        return fin_path

    def encrypt(self, path: str) -> str:
        # returns new path!
        # We dont need any path validation, its done in File.validatePath()
        if self.state != E_State.IDLE:
            return path # DO NOTHING

        self.state = E_State.ENCRYPT

        fin_path = path + ".crypt"
        self.cmd.cmd = self.MODE_CMD[self.mode] + "-e -iv " + self.iv + " -k " + self.key.value + " -in '" + path + "' -out '" + fin_path + "'"
        self.cmd.start()

        self.refresh()
        return fin_path

    def _asdict(self) -> dict:
        self.refresh()
        data = {
            "state": self.state.name,
            "mode": self.mode.name,
            "key": self.key._asdict(),
            "cmd": self.cmd._asdict()
        }
        return data
    
    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

import json
from typing import List
from enum import Enum

from backend.Command import Command

class KeyLength(Enum):
    short = 2048
    medium = 4096
    long = 8192

class Key:

    def __init__(self, length: KeyLength = KeyLength.medium):
        self.cmd = Command("openssl rand " + str(length.value), raw=True)
        self.cmd.wait()
        self.length = length
        self.value = self.cmd.stdout[0]

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
    DECRYPT = 2

class E_Mode(Enum):
    AES128CBC = 1
    AES256CBC = 2
    
    # ToDo
    AES128CTR = 3
    AES256CTR = 4

class Encryption:

    def __init__(self, key: Key, mode: E_Mode = E_Mode.AES256CBC):
        self.key = key
        self.mode = mode
        self.cmd = Command("openssl rand -hex 16")
        self.cmd.wait()
        self.iv = self.cmd.stdout[0]
        self.state: E_State = E_State.IDLE
        
    def refresh(self) -> None:
        self.cmd.status()
        
        if self.state in [E_State.ENCRYPT, E_State.DECRYPT ] :
            # 
            # is command successful terminated?
            pass
        
        else:
            # Continue IDLEing
            pass


    def encrypt(self) -> None:
        self.refresh()
        if self.cmd.running:
            return

        

    def _asdict(self) -> dict:
        self.refresh()
        data = {
            "state": self.state.name,
            "mode": self.mode.name,
            "key": self.key._asdict(),
            "iv": self.iv
        }
        return data
    
    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

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
        data = {
            "length": self.length.name,
            "value": self.value
        }

        return data

class E_Mode(Enum):
    AES128 = 1
    AES256 = 2

class Encryption:

    def __init__(self, key: Key, mode: E_Mode = E_Mode.AES256):
        self.key = key
        self.mode = mode
        self.cmd = Command("openssl rand -hex 16")
        self.cmd.wait()
        self.iv = self.cmd.stdout[0]

    def _asdict(self) -> dict:
        data = {
            "mode": self.mode.name,
            "key": self.key._asdict(),
            "iv": self.iv
        }

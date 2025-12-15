import json
import os
from pathlib import Path

from backend.Checksum import Checksum
from backend.Command import Command
from backend.Encryption import Encryption

DEBUG: bool = True

class File:

    def __init__(self, id: int, path: str, createFile: bool = False) -> None:
        # TODO:
        #    1. self.path must start with /
        #    2. self.relative_path must start with ./
        self.cmd: Command = Command("") # main command construct
        if createFile:
            # raises PermissonError (if unsufficient perms detected)
            self.touch(path)

        self.validatePath(path)
        self.id: int = id
        self.size : int
        self.name : str
        self.path: str = path
        self.relative_path: str = ""    # this comes handy when restoring a tape
        self.cksum : Checksum = Checksum(self.path) 
        self.encryption_scheme: Encryption = None

        self.readSize()

    def touch(self, path: str) -> None:
        try:
            Path(path).touch(exist_ok=True)
        except PermissionError:
            raise PermissionError("[ERROR] Insufficient permissions on '" + path + "'")
        except Exception:
            raise

    def validatePath(self, path: str):
        self.cmd.cmd = "find '" + path +  "'"
        self.cmd.start()    # we currently in __init__ therefor self.path does not exist

        if self.cmd.exitCode == 1:
            raise FileNotFoundError("[ERROR] Invalid Path given!") # This backend has no file-by-file interface
        else:
            self.path = path
            self.name = path.split('/')[-1]

    def readSize(self) -> None:
        self.cmd.cmd = "stat -c %s '" + self.path + "'"
        self.cmd.start()
        try:
            self.size = int(self.cmd.stdout[0])
        except TypeError:
            self.size = 0
        except IndexError:
            self.size = 0
        except Exception as e:
            print("[ERROR] cannot determine file size of file" + str(self) + "   Exception: " + str(e))

    def setChecksum(self, c: Checksum) -> None:
        self.cksum = c
        self.cksum.cmd.filesize = self.size
        self.cksum.file_path = self.path

    def decrypt(self, encryption_scheme: Encryption) -> None:
        self.encryption_scheme = encryption_scheme
        self.path = encryption_scheme.decrypt(self.path)
    
    def encrypt(self, encryption_scheme: Encryption) -> None:
        self.encryption_scheme = encryption_scheme
        self.path = encryption_scheme.encrypt(self.path)

    def append(self, text: str):
        # Needed in order to append a given string to a file
        # In order to create a txt file you shall do:
        # text = File()
        # text.touch()
        # text.append("This is a wonderful text")
        # cmd.cmd = "cat " + text.path
        # cmd.wait()
        # "This is a wonderful text" == cmd.stdout[0]
        return
        #try:
        #    Path(path.)

    def createChecksum(self) -> None:
        self.cksum.create() # start the checksumming process

    def validateIntegrity(self) -> None:
        if len(self.cksum.value) == 0:
            return
        self.cksum.validate(self.cksum.value)

    def remove(self) -> None:
        # This removes the file from the filesystem and resets `self`
        try:
            os.remove(self.path)
        except PermissionError:
            raise PermissionError("[ERROR] Could not delete File '" + self.path + "'")
        except:
            raise

        self.id = -1
        self.size = -1
        self.name = ""
        self.path = ""
        self.relative_path = ""
        self.cksum = Checksum("")

    def _refresh(self):
        self.cksum._status()    # get current status

    def _asdict(self) -> dict:
        self._refresh()
        data = {
            "id": self.id,
            "size": self.size,
            "name": self.name,
            "path": self.path,
            "rel_path": self.relative_path,
            "last_command": self.cmd._asdict(),
            "cksum": self.cksum._asdict(),
        }
        if self.encryption_scheme is not None:
            data.update({"encryption": self.encryption_scheme._asdict()})
        return data

    def __str__(self) -> str:
        return "{\"FILE\" :" + json.dumps(self._asdict(), indent=2) + "}"

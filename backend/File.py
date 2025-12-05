import json
import os
from pathlib import Path

from backend.Checksum import Checksum
from backend.Command import Command

DEBUG: bool = True

class File:

    def setChecksum(self, c: Checksum) -> None:
        self.cksum = c

    def touch(self, path: str) -> None:
        try:
            Path(path).touch(exist_ok=True)
        except PermissionError:
            raise PermissionError("[ERROR] Insufficient permissions on '" + path + "'")
        except Exception:
            raise

    def append(text: str):
        return
        #try:
        #    Path(path.)

    def validatePath(self, path: str):
        # This checks whether the given path is valid
        # and sets self.path accordingly
        self.cmd = Command("find '" + path +  "'")
        self.cmd.start()

        if self.cmd.exitCode == 1:
            raise FileNotFoundError("[ERROR] Invalid Path given!")
        else:
            self.path = path
            self.name = path.split('/')[-1]

    def readSize(self) -> None:
        self.cmd: Command = Command("stat -c %s '" + self.path + "'")
        self.cmd.start()
        try:
            self.size = self.cmd.stdout[0]
        except TypeError:
            self.size = 0
        except IndexError:
            self.size = 0
        except Exception as e:
            print("[ERROR] cannot determine file size of file" + str(self) + "   Exception: " + str(e))
        
    def createChecksum(self) -> None:
        self.cksum.create() # start the checksumming process


    def remove(self) -> None:
        # This removes the file from the filesystem and resets `self`
        try:
            os.remove(self.path)
        except PermissionError:
            raise PermissionError("[ERROR] Could not delete File '" + self.path + "'")
        except:
            raise

        self.id = None
        self.size = None
        self.name = None
        self.path = None
        self.cksum = None
        self.cmd = None

    """_summary_ File.()
        - createFile = True will `touch` file.path
        - id is some arbitrary number you can like
        - path is the path file... like the path yk... 
    """

    def _refresh(self):
        self.cksum._status()    # get current status


    def __init__(self, id: int, path: str, createFile: bool = False) -> None:
        if createFile:
            # raises PermissonError (if unsufficient perms detected)
            self.touch(path)

        self.validatePath(path)
        self.id: int = id
        self.size : int
        self.name : str
        self.path: str = path
        self.cksum : Checksum = Checksum(self.path) 
        self.cmd: Command

        self.readSize()

    def _asdict(self) -> dict:
        data = {
            "id": self.id,
            "size": self.size,
            "name": self.name,
            "path": self.path,
            "last_command": self.cmd._asdict(),
            "cksum": self.cksum._asdict()
        }
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict())

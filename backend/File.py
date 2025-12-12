import json
import os
from pathlib import Path

from backend.Checksum import Checksum
from backend.Command import Command
from backend.Encryption import *

DEBUG: bool = True

#TODO ADD ENCRYPTION
"""
ENCRYPTION:
Needed:
    - Master Key Phrase (2048/4096/8192)
    - Type (aes-128-cbc/aes-256-cbc/aes-128-ctr/aes-256-ctr)

"""
class File:
    
    def decrypt(self, encryption_scheme: Encryption) -> None:
        self.encryption_scheme = encryption_scheme
        self.path = encryption_scheme.decrypt(self.path)
    
    def encrypt(self, encryption_scheme: Encryption) -> None:
        self.encryption_scheme = encryption_scheme
        self.path = encryption_scheme.encrypt(self.path)

    def setChecksum(self, c: Checksum) -> None:
        self.cksum = c
        self.cksum.cmd.filesize = self.size

    def touch(self, path: str) -> None:
        try:
            Path(path).touch(exist_ok=True)
        except PermissionError:
            raise PermissionError("[ERROR] Insufficient permissions on '" + path + "'")
        except Exception:
            raise

    def append(self, text: str):
        # Needed in order to append a given string to a file
        # In order to create a txt file you shall do:
        # text = File()
        # text.touch()
        # text.append("This is a wonderful text")
        # cmd = Command("cat " + text.path)
        # cmd.wait()
        # "This is a wonderful text" == cmd.stdout[0]
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
            self.size = int(self.cmd.stdout[0])
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

        self.id = -1
        self.size = -1
        self.name = ""
        self.path = ""
        self.relative_path = ""
        self.cksum = Checksum("")
        self.cmd = Command("")

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
        self.relative_path: str = ""    # this comes handy when restoring a tape
        self.cksum : Checksum = Checksum(self.path) 
        self.encryption_scheme: Encryption = None
        self.cmd: Command

        self.readSize()

    def _asdict(self) -> dict:
        data = {
            "id": self.id,
            "size": self.size,
            "name": self.name,
            "path": self.path,
            "rel_path": self.relative_path,
            "last_command": self.cmd._asdict(),
            "cksum": self.cksum._asdict(),
        }
        if self.encryption_scheme != None:
            data.update({"encryption": self.encryption_scheme._asdict()})
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict())

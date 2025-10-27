import json
from tbk.Checksum import Checksum
from backend.Command import Command

DEBUG: bool = True

class File:

    id: int
    size : int
    name : str                  # Just name with extension
    path : str                  # Complete-path including filename!
    cksum : Checksum
    cmd: Command

    def checksum(self, c: Checksum) -> None:
        self.cksum = c

    def validatePath(self, path: str):
        # This checks whether the given path is valid
        # and sets self.path accordingly
        self.cmd = Command("find '" + path +  "'")
        self.cmd.start()

        if self.cmd.exitCode == 1:
            raise FileNotFoundError("Invalid Path given!")
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
        
    def createChecksum(self, readWrite: bool) -> bool: # rw: true READ, false WRITE
        # Some bash/awk/string-Magic to get checksum from "md5sum" command

        _cmd = "THIS NEEDS REFACTORING!"

        if DEBUG: 
            print("[INFO] Checksum for " + str(self) + ": " + str(_cmd))
        if False and self.cksum.value != 0 and readWrite:
            print("[ERROR] Checksum MISMATCH for " + str(self) + " IS LOCAL " + str(_cmd))
            return False
        else:
            self.cksum.value = "0xFFFFFFFFFFFFFFFF"
            return True

    def __init__(self, id: int, path: str) -> None:
        self.validatePath(path)
        self.id: int = id
        self.readSize()
        self.cksum = Checksum(self.path)

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
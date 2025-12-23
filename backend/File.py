import json
import os
from enum import Enum
from pathlib import Path

from backend.Checksum import Checksum
from backend.Command import Command
from backend.Encryption import Encryption

DEBUG: bool = True

class FileState(Enum):
    INIT = 1
    ENCRYPT = 2
    DECRYPT = 3
    CHECKING = 4
    MISMATCH = 5
    REMOVING = 6
    IDLE = 7
    ERROR = 8

class File:

    """
    File interface:
    - File.__init__()           Needs: File-ID and path.
                                Provides: 
                                  - path integrity -> raises FileNotFoundError("…")
                                  - absolute and relative path
                                  - file size (in bytes)
                                  - Checksum object
                                  - Encryption object
                                  - creates file on demand
    - File._refresh()           Does process finalization and changes states accordingly
    - File._asdict()            Returns a JSON dict to caller
    - File.__str__()            Returns a pretty JSON string
    - File.wait()               waits until File.state == FileState.IDLE
    -=== BASIC I/O ===============================================================================-
    - File.touch()              Raises PermissonError if unsufficient perms are given
    - File.validatePath()       Does look for path and creates abs/rel path
    - File.readSize()           Gets File Size
    -=== CHECKSUMMING ============================================================================-
    - File.setChecksum()        Overwrites default checksum object
    - File.createChecksum()     Starts checksumming process
    - File.validateIntegrity()  Starts a validation process (instead of JUST creating A checksum)
    -=== ENCRYPTION ==============================================================================-
    - File.encrypt()            START the encryption process
                                - keepOrig = False calls File.remove() after exit_code != 0
    - File.decrypt()            START the DECRYPTION process with encryption scheme "e"
    """

    def __init__(self, id: int, path: str, createFile: bool = False) -> None:
        """
        Vars:
        - self.state                Current State of File Operation (CSFO)
        - self.id                   arb ID (user specified)
        - self.name                 filename, derived from path
        - self.size                 size in Bytes
        - self.path                 absolute path for further commands
        - self.name                 file name (last substring with no slashes)
        - self.parent               parent dir of FILE
        - self.cmd                  Command object for any arb commands
        - self.cksum                Checksum object
        - self.encryption_scheme    Encryption object for secrets and options

        Raises:
        - FileNotFoundError         If createFile != True AND input-path invalid
        - PermissionError           Insufficient permissions in parent directory
        """

        self.state: FileState = FileState.INIT
        self.cmd: Command = Command("")
        if createFile:
            self.touch(path)

        self.validatePath(path)
        self.id: int = id
        self.size : int
        self.cksum : Checksum = Checksum(self.path) 
        self.encryption_scheme: Encryption = None

        self.readSize()
        self.state = FileState.IDLE

    def _refresh(self):
        self.cksum._status()    # get current status

    def wait(self):
        pass

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

    # === BASIC I/O ===============================================================================
    def touch(self, path: str) -> None:
        try:
            Path(path).touch(exist_ok=True)
        except PermissionError:
            self.state = FileState.ERROR
            raise PermissionError("[ERROR] Insufficient permissions on '" + path + "'")
        except Exception:
            self.state = FileState.ERROR
            raise

    def validatePath(self, path: str) -> None:
        self.cmd.cmd = "realpath '" + path +  "'"
        self.cmd.wait()    # we currently in __init__ therefor self.path does not exist

        if self.cmd.exitCode == 1:
            self.state = FileState.ERROR
            raise FileNotFoundError("[ERROR] Invalid Path given!") # This backend has no file-by-file interface

        self.path = self.cmd.stdout[0]
        self.name = path.split('/')[-1]
        self.parent = path.split(self.name)[0][:-1]  # get parent dir, trim last char '/'


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

    def destroy(self) -> None:
        # This calles file.remove() and destroys object completely
        self.id = -1
        self.size = -1
        self.name = ""
        self.path = ""
        self.relative_path = ""
        self.cksum = Checksum("")    # Todo call "remove(File)" so this object is indeed gone

    def remove(self) -> None:   # This removes FILE from filesystem
        # This removes the file from the filesystem and resets `self`
        try:
            os.remove(self.path)
        except PermissionError:
            raise PermissionError("[ERROR] Could not delete File '" + self.path + "'")
        except:
            raise

    # === CHECKSUMMING ============================================================================

    def setChecksum(self, c: Checksum) -> None:
        self.cksum = c
        self.cksum.cmd.filesize = self.size
        self.cksum.file_path = self.path

    def createChecksum(self) -> None:
        self.cksum.create() # start the checksumming process

    def validateIntegrity(self) -> None:
        if len(self.cksum.value) == 0:
            return
        self.cksum.validate(self.cksum.value)

    # === ENCRYPTION ==============================================================================

    def decrypt(self, encryption_scheme: Encryption, keepOrig: bool = True) -> None:
        self.encryption_scheme = encryption_scheme
        self.path = encryption_scheme.decrypt(self.path)
    
    def encrypt(self, encryption_scheme: Encryption, keepOrig: bool = True) -> None:
        self.encryption_scheme = encryption_scheme
        self.path = encryption_scheme.encrypt(self.path)



import json
import os
from enum import Enum
from pathlib import Path
from typing import List

from backend.Checksum import Checksum, ChecksumState
from backend.Command import Command
from backend.Encryption import E_State, Encryption, Key

DEBUG: bool = True

class FilePath():

    """
    #### === FILEPATH =========================================================
    This Class has those different variables for dynamic path management.  
    Example File: `/opt/project/to_tape/backup.img`  
    Context: `/opt/project` (current "./" directory)

    | Variable         | Description                        | Example                           |
    |------------------|------------------------------------|-----------------------------------|
    | FilePath.path    | Complete Path                      | `/opt/project/to_tape/backup.img` |
    | FilePath.name    | File name with extension           | `backup.img`                      |
    | FilePath.parent  | Parent directory of current file   | `/opt/project/to_tape`            |
    | FilePath.context | current context in file system     | `/opt/project`                    |
    | FilePath.relPath | path in relation to context        | `./to_tape/backup.img`            |
    """

    def __init__(self, path: str, context: str) -> None:
        self.path: str = path
        self.context: str = context
        self.update()

    def update(self) -> None:
        self.validate()
        self.refresh() 

    def validate(self) -> None:

        # Context validation
        if not self.path.startswith(self.context):
            raise FileNotFoundError("[ERROR] Invalid context path!")

        # Full path validation
        cmd: Command = Command("find " + self.path)
        cmd.wait()

        try:
            if cmd.stdout[0] != self.path:
                raise FileNotFoundError("[ERROR] Invalid Path given!")
        except IndexError: # if len(stdout) == 0...
            raise FileNotFoundError("[ERROR] Invalid Path given!")

        if cmd.exitCode != 0:
            raise SystemError("[ERROR] FIND command on path failed with unkown reason!")

    def refresh(self) -> None:
        self.relPath: str = os.path.relpath(self.path, self.context)
        self.name: str = os.path.basename(self.path)
        self.parent: str = os.path.dirname(self.path)

    def _asdict(self) -> dict:
        return {
            "path": self.path,
            "context": self.context,
            "relPath": self.relPath,
            "name": self.name,
            "parent": self.parent
        }

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

class FileState(Enum):
    INIT = 1
    ENCRYPT = 2
    DECRYPT = 3
    CKSUM_CALC = 4
    VALIDATING = 5
    MISMATCH = 6
    REMOVING = 7
    IDLE = 8
    REMOVED = 9
    ERROR = 99

class File:

    """
    ### === FILE =============================================================

    File.__init__(id: int, path: str, createFile: bool = False):
    - Requires:
        - A unique ID (integer)
        - File path (string)
    - Accepts:
        - createFile (bool): Creates the file if it does not exist (optional)
    - Responsibilities:
        - Validates file path integrity → raises FileNotFoundError if invalid
        - Generates absolute and relative file paths
        - Retrieves the size of the file in bytes
        - Initializes a Checksum object
        - Initializes an Encryption object

    ### --- EXCEPTIONS ------------------------------------------------------

    **FileNotFoundError:** Raised if the input path is invalid and createFile is False.  
    **RuntimeError:** Raised if still in INIT state and smth gets called
    **PermissionError:** Raised when filesystem operations (e.g., touch, remove) lack required permissions.

    **Core Functionality:**
    | `File.`         | Description                                                          |
    |-----------------|----------------------------------------------------------------------|
    | `File.touch()`  | Creates an empty file on the filesystem if it does not already exist |
    | `File.remove()` | Deletes the file from the filesystem                                 |
    | `File.append()` | Appends a given String to current (text) file                        |

    **Object Related:**
    | `File.`          | Description                                                       |
    |------------------|-------------------------------------------------------------------|
    | `File.wait()`    | Waits for the state of the file operation to reach FileState.IDLE |
    | `File.refresh()` | Refreshes the state of the file, processing associated variables  |
    | `File.destroy()` | Removes the file and deallocates associated resources             |
    | `File._asdict()` | Returns a JSON dictionary representation of the File object       |
    | `File.__str__()` | Returns a pretty JSON string representation of the File object    |

    **Checksumming:**
    | `File.`                    | Description                                     |
    |----------------------------|-------------------------------------------------|
    | `File.createChecksum()`    | Computes a checksum for the file                |
    | `File.validateIntegrity()` | Validates file integrity based on its checksum  |

    **Encryption:**
    | `File.`          | Description                                                         |
    |------------------|---------------------------------------------------------------------|
    | `File.encrypt()` | Encrypts the file and optionally removes the original after success |
    | `File.decrypt()` | Decrypts the file using a specified encryption scheme               |

    ### === VARIABLES ======================================================

    | Variable          | Type        | Description                                        |
    |-------------------|-------------|----------------------------------------------------|
    | `self.id`         | `int`       | Custom user-defined ID for the file                |
    | `self.path`       | `FilePath`  | Absolute and complete file path                    |
    | `self.size`       | `int`       | File size in bytes                                 |
    | `self.cmd`        | `Command`   | Command object for executing subprocesses          |
    | `self.cksum`      | `Checksum`  | Checksum object for file integrity verification    |
    | `self.state`      | `FileState` | Current operational state of the file              |
    | `self.state_msg`  | `List[str]` | Logs and messages corresponding to state or errors |

    **Checksum Handling**
    - Initialize: Create a new Checksum instance for the file.
    - Validate: Verify file consistency and integrity using checksums.
    - Refresh: Refresh checksum-related status data during processes.

    **Encryption Handling**
    - Integrates Encryption objects to provide:
        - File encryption (`File.encrypt()`)
        - File decryption (`File.decrypt()`)

    #### === DESIGN PRINCIPLES ==============================================

    The `File` class facilitates file system management operations, wrapping functionality for
    encryption, checksums, and command execution. Its modular design ensures readability,
    flexibility, and integration with additional backend tools for operational enhancements.

    """

    def __init__(self, id: int, path: str, path_context: str, createFile: bool = False) -> None:
        self.state: FileState = FileState.INIT
        self.state_msg: List[str] = []
        self.cmd: Command = Command("")

        self.id: int = id
        self.size : int = -1

        if createFile:
            self.touch(path)

        self.path: FilePath = FilePath(path, path_context)
        self.cksum: Checksum = Checksum(self.path.path)
        self.encryption_scheme: Encryption = Encryption(Key())

        self.readSize()

        self.state = FileState.IDLE

# === PUBLIC METHODS ==========================================================

# --- CORE FUNCTIONALITY ------------------------------------------------------

    def touch(self, path: str) -> None:

        if self.state not in {FileState.REMOVED, 
                              FileState.IDLE, 
                              FileState.INIT}:
            return

        try:
            Path(path).touch(exist_ok=True) # Is instant, no background command needed

        except PermissionError:
            self.state = FileState.ERROR
            self.state_msg.append("[ERROR] Insufficient permissions on '" + path + "'")
            raise PermissionError("[ERROR] Insufficient permissions on '" + path + "'")

        except Exception as e:
            self.state = FileState.ERROR
            self.state_msg.append("[ERROR] unhandled error occured during creation of file '" + path + "'" + " Exception: " + str(e))
            raise

        if self.state is FileState.INIT:
            return  # returns early bc we are still initializing

        self.refresh()

    def remove(self) -> None:   # This removes FILE from filesystem
        self.state = FileState.REMOVING
        try:
            os.remove(self.path.path)    # TODO Check if this blocks!
            self.refresh()
        except PermissionError:
            self.state_msg.append("[ERROR] Deletion failed, permisson error occured '" + str(self.path) + "'")
            raise
        except Exception as e:
            self.state_msg.append("[ERROR] Deletion failed, unkown error" + str(self) + "   Exception: " + str(e))
            raise

    def append(self, text: str):
        if self.state in {FileState.IDLE}:
            with open(self.path.path, "a") as file:
                file.write(text)

            self.readSize()


# --- OBJECT RELATED ----------------------------------------------------------

    def wait(self) -> None:
        if self.state in {FileState.IDLE, 
                          FileState.MISMATCH,
                          FileState.REMOVED,
                          FileState.ERROR}:
            return

        if self.state is FileState.REMOVING:
            self.cmd.wait()
            self.refresh()
            return

        if self.state in {FileState.ENCRYPT, FileState.DECRYPT}:
            self.encryption_scheme.cmd.wait()
            self.refresh()
            return

        if self.state in {FileState.VALIDATING, FileState.CKSUM_CALC}:
            self.cksum.wait()
            self.refresh()
            return

    def refresh(self) -> None:

        if self.state is FileState.INIT:    # this is purely a error that shall not occur in prod
            raise RuntimeError("[ERROR] FILE is still initializing but should be initialized by now!")

        if self.state in {FileState.ERROR,
                          FileState.IDLE,
                          FileState.MISMATCH,
                          FileState.REMOVED}:
            return # Do nothing when in PERMANENT state

        if self.state is FileState.REMOVING:
            try:
                self.path.validate()    # Validate Path
            except FileNotFoundError:   # Set flags
                self.state = FileState.REMOVED
                self.size = -1

                if not self.encryption_scheme.keepOrig:
                    self.state = FileState.IDLE
                    self.path.path = self.encryption_scheme.targetPath
                    self.path.update()
                    self.readSize()
                return

        if self.state is FileState.CKSUM_CALC:
            # We are currently calculating a Checksum on File (w/o validation).
            self.cksum._status()

            if self.cksum.state == ChecksumState.IDLE:
                self.state = FileState.IDLE
                return

            if self.cksum.state == ChecksumState.ERROR:
                self.state_msg.append("[ERROR] Checksum creation failed!")
                self.state = FileState.ERROR
                return

        if self.state is FileState.VALIDATING:
            # We are currently validating FILE to a known-good checksum
            self.cksum._status()
            match (self.cksum.state):
                case ChecksumState.IDLE:
                    self.state = FileState.IDLE
                    return
                case ChecksumState.MISMATCH:
                    self.state_msg.append("[ERROR] Checksum mismatch!")
                    self.state = FileState.MISMATCH
                    return
                case ChecksumState.ERROR:
                    self.state_msg.append("[ERROR] Checksum validation failed with unkown error!")
                    self.state = FileState.ERROR
                    return

        if self.state in {FileState.ENCRYPT, FileState.DECRYPT}:
            self.encryption_scheme._asdict()

            match self.encryption_scheme.state:
                case E_State.IDLE:
                    self.state = FileState.IDLE
                    self.readSize()

                case E_State.ERROR:
                    self.state = FileState.ERROR
                    self.state_msg.append("[ERROR] Encrypt/Decrypt failed with unkown reason")
                    return

            if self.encryption_scheme.keepOrig:
                self.path.path = self.encryption_scheme.targetPath
                self.path.update()
                self.readSize()
            else:
                self.remove()

    def _asdict(self) -> dict:
        self.refresh()
        data = {
            "id": self.id,
            "state": self.state.name,
            "messages": self.state_msg,
            "size": self.size,
            "path": self.path._asdict(),
            "last_command": self.cmd._asdict(),
            "cksum": self.cksum._asdict(),
            "encryption": self.encryption_scheme._asdict()
        }
        return data

    def __str__(self) -> str:
        return "{\"FILE\" :" + json.dumps(self._asdict(), indent=2) + "}"

# --- CHECKSUMMING ------------------------------------------------------------

    def setChecksum(self, c: Checksum) -> None:
        self.cksum = c
        self.cksum.cmd.filesize = self.size

    def createChecksum(self) -> None:
        if self.cksum.file_path != self.path.path:
            self.cksum.file_path = self.path.path

        if self.state is FileState.IDLE:
            self.state = FileState.CKSUM_CALC
            self.cksum.create() # start the checksumming process

    def validateIntegrity(self, validationTarget: str) -> None: 
        if self.cksum.file_path != self.path.path:
            self.cksum.file_path = self.path.path

        self.state = FileState.VALIDATING
        self.cksum.validate(validationTarget)

# --- ENCRYPTION --------------------------------------------------------------

    def decrypt(self) -> None:
        if self.state is FileState.IDLE:
            self.state = FileState.DECRYPT
            self.encryption_scheme.decrypt(self.path.path)

    def encrypt(self) -> None:
        if self.state is FileState.IDLE:
            self.state = FileState.ENCRYPT
            self.encryption_scheme.encrypt(self.path.path)

# === INTERNAL METHOD =========================================================

    def readSize(self) -> None:
        self.cmd.reset()
        self.cmd.cmd = "stat -c %s '" + self.path.path + "'"
        self.cmd.wait()

        try:
            self.size = int(self.cmd.stdout[0])
        except TypeError:
            self.size = 0
        except IndexError:
            self.size = 0
        except Exception as e:
            self.state_msg.append("[ERROR] cannot determine file size of file" + str(self) + "   Exception: " + str(e))
            raise

        self.cksum.cmd.filesize = self.size
        self.encryption_scheme.cmd.filesize = self.size

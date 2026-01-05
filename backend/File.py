import json
import os
from enum import Enum
from pathlib import Path
from typing import List

from backend.Checksum import Checksum, ChecksumState
from backend.Command import Command
from backend.Encryption import Encryption

DEBUG: bool = True

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
    | `self.path`       | `str`       | Absolute and complete file path                    |
    | `self.name`       | `str`       | File name (derived from path)                      |
    | `self.size`       | `int`       | File size in bytes                                 |
    | `self.parent`     | `str`       | Parent directory of the file                       |
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

    def __init__(self, id: int, path: str, createFile: bool = False) -> None:
        self.state: FileState = FileState.INIT
        self.state_msg: List[str] = []
        self.cmd: Command = Command("")
        self.cmd.quiet = False

        self.id: int = id
        self.size : int = -1

        if createFile:
            self.touch(path)

        self.validatePath(path)
        self.readSize()

        self.cksum: Checksum = Checksum(self.path)
        self.encryption_scheme: Encryption = None

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
            return  # call self.refresh() is needed for all other operations

        self.refresh()

    def remove(self) -> None:   # This removes FILE from filesystem
        # This removes the file from the filesystem
        try:
            os.remove(self.path)    # TODO Check if this blocks!
        except PermissionError:
            self.state_msg.append("[ERROR] Deletion failed, permisson error occured '" + self.path + "'")
            raise
        except Exception as e:
            self.state_msg.append("[ERROR] Deletion failed, unkown error" + str(self) + "   Exception: " + str(e))
            raise

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
            self.encryption_scheme.refresh()
            return

        if self.state in {FileState.VALIDATING, FileState.CKSUM_CALC}:
            self.cksum.wait()

    def destroy(self, removeFileFrom) -> None:
        # This calles file.remove() and destroys object completely
        self.id = -1
        self.size = -1
        self.name = ""
        self.path = ""
        self.relative_path = ""
        self.cksum = Checksum("")    # Todo call "remove(File)" so this object is indeed gone

    def refresh(self) -> None:

        if self.state is FileState.INIT:
            return
            raise RuntimeError("[ERROR] FILE is still initializing but should be initialized by now!")

        if self.state in {FileState.ERROR,
                          FileState.INIT,
                          FileState.IDLE,
                          FileState.MISMATCH,
                          FileState.REMOVED}:
            return # Do nothing when in PERMANENT state

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

        """TODO
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
        """

        match self.state:
            case FileState.CHECKING:
                pass
            case FileState.ENCRYPT:
                pass
            case FileState.DECRYPT:
                pass
            case FileState.REMOVING:
                self.cmd.wait() # FIXME
                self.state = FileState.REMOVED
                pass
        self.cksum._status()    # get current status

    def _asdict(self) -> dict:
        self.refresh()
        data = {
            "id": self.id,
            "size": self.size,
            "name": self.name,
            "path": self.path,
            "last_command": self.cmd._asdict(),
            "cksum": self.cksum._asdict(),
        }
        if self.encryption_scheme is not None:
            data.update({"encryption": self.encryption_scheme._asdict()})
        return data

    def __str__(self) -> str:
        return "{\"FILE\" :" + json.dumps(self._asdict(), indent=2) + "}"

# --- CHECKSUMMING ------------------------------------------------------------

    def setChecksum(self, c: Checksum) -> None:
        self.cksum = c
        self.cksum.cmd.filesize = self.size
        self.cksum.file_path = self.path

    def createChecksum(self) -> None:
        if self.state is FileState.IDLE:
            self.cksum.create() # start the checksumming process
            self.state = FileState.CKSUM_CALC

    def validateIntegrity(self) -> None: 
        if len(self.cksum.value) == 0:
            return # TODO Maybe raise a SystemError
        self.cksum.validate(self.cksum.value)

# --- ENCRYPTION --------------------------------------------------------------

    def decrypt(self, encryption_scheme: Encryption, keepOrig: bool = True) -> None:
        self.encryption_scheme = encryption_scheme
        self.path = encryption_scheme.decrypt(self.path)

    def encrypt(self, encryption_scheme: Encryption, keepOrig: bool = True) -> None:
        self.encryption_scheme = encryption_scheme
        self.path = encryption_scheme.encrypt(self.path)

# === INTERNAL METHODS ========================================================

    def validatePath(self, path: str) -> None:
        self.cmd.reset()
        self.cmd.cmd = "realpath '" + path +  "'"
        self.cmd.wait()    # we currently in __init__ therefore self.path does not exist

        if self.cmd.exitCode == 1:
            self.state = FileState.ERROR
            raise FileNotFoundError("[ERROR] Invalid Path given!") # This backend has no file-by-file interface

        self.path = self.cmd.stdout[0]
        self.name = path.split('/')[-1]
        self.parent = path.split(self.name)[0][:-1]  # get parent dir, trim last char '/'

    def readSize(self) -> None:
        self.cmd.reset()
        self.cmd.cmd = "stat -c %s '" + self.path + "'"
        self.cmd.wait()
        try:
            self.size = int(self.cmd.stdout[0])
        except TypeError:
            self.size = 0
        except IndexError:
            self.size = 0
        except Exception as e:
            self.state_msg.append("[ERROR] cannot determine file size of file" + str(self) + "   Exception: " + str(e))

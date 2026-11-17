import json
import os
from enum import Enum
from pathlib import Path
from typing import List, Set, Tuple, TYPE_CHECKING

from backend.Checksum import Checksum, ChecksumState, ChecksumType
from backend.Command import Command
from backend.Encryption import E_Mode, E_State, Encryption, Key
from backend.Job import EntryState, Job

if TYPE_CHECKING:       # TapeDrive imports File
    from backend.TapeDrive import TapeDrive

class FilePath():

    """#### === FILEPATH =========================================================
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
        if not os.path.exists(self.path):
            raise FileNotFoundError("[ERROR] Invalid Path given!")

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
    IDLE = 8
    REMOVED = 9
    QUEUED = 10         # a phase waits in the Job queue
    WRITE = 11
    READ = 12
    ERROR = 99

class File:

    """
    ### === FILE =============================================================

    One file on disk, which goes through all phases itself. A phase does not run anything:
    it builds a `Command`, hands it to `Job` and returns the Job entry id. The next phase
    passes that id as `dependsOn`, so a chain is queued in one go. A phase that has nothing
    to do (checksum type NONE, encryption NONE) returns `dependsOn` unchanged.

    | `File.`                                  | Phase                                          |
    |------------------------------------------|------------------------------------------------|
    | `Validate()`                             | no checksum yet: create it, else compare to it |
    | `Encrypt(target="")`                     | plain file -> `target` (default `<path>.crypt`) |
    | `Write(tapeDrive)`                       | (encrypted) file -> tape                       |
    | `Read(tapeDrive, target)`                | next tape file -> `target`                     |
    | `Decrypt(target)`                        | encrypted file -> `target`                     |

    All take `runlist=""` and `dependsOn=""`. `Read()` reads at the current tape position,
    positioning is the job of the TapeDrive.

    `File.state` is derived from the Job entries of the phases, it never has to be set:

        IDLE -> QUEUED -> CKSUM_CALC | VALIDATING | ENCRYPT | WRITE | READ | DECRYPT -> IDLE
                                                   \\-> MISMATCH | ERROR (final)

    The results are taken over whenever `state`, `cksum` or `encryption_scheme` is read, so
    `file.cksum.value` is current as soon as the phase has finished.
    One checksum and one encryption can be pending at a time; a second `Validate()` /
    `Encrypt()` / `Decrypt()` before the first one has run raises `RuntimeError`.

    `File.path` always stays the original file. `File.cryptPath` is the encrypted copy and
    `File.where` the plain file `Validate()` looks at (the original, or what `Read()` /
    `Decrypt()` restored).

    Plain file system operations are instant and need no Job: `touch()`, `remove()`,
    `append(text)`, `readSize()`.
    """

    def __init__(self, id: int, path: str, path_context: str, createFile: bool = False) -> None:
        self._state: FileState = FileState.INIT
        self.state_msg: List[str] = []
        self.cmd: Command = Command("")
        self.entries: List[Tuple[FileState, str]] = []     # (phase, Job entry id), in the order added
        self._taken: Set[str] = set()                      # entries whose result is already taken over
        self._settled: int = 0                             # number of entries, when all of them were finished

        self.id: int = id
        self.size : int = -1

        if createFile:
            self.touch(path)

        self.path: FilePath = FilePath(path, path_context)
        self._cksum: Checksum = Checksum(self.path.path)
        self._encryption: Encryption = Encryption(Key())
        self.cryptPath: str = ""
        self.where: str = self.path.path

        self.readSize()

        self._state = FileState.IDLE

    @property
    def state(self) -> FileState:
        self.refresh()
        return self._state

    @state.setter
    def state(self, value: FileState) -> None:
        self._state = value

    # Reading these also takes over the results of finished phases, so they are never stale
    @property
    def cksum(self) -> Checksum:
        self.refresh()
        return self._cksum

    @cksum.setter
    def cksum(self, value: Checksum) -> None:
        self._cksum = value

    @property
    def encryption_scheme(self) -> Encryption:
        self.refresh()
        return self._encryption

    @encryption_scheme.setter
    def encryption_scheme(self, value: Encryption) -> None:
        self._encryption = value

# === PHASES ===================================================================

    def Validate(self, runlist: str = "", dependsOn: str = "") -> str:
        self._accept()
        if self.cksum.type is ChecksumType.NONE:
            return dependsOn
        if self.cksum.state not in {ChecksumState.IDLE, ChecksumState.MISMATCH}:
            raise RuntimeError("[ERROR] A checksum is still pending")

        self.cksum.file_path = self.where
        if self.cksum.value:
            self.cksum.validate(self.cksum.value)
            phase: FileState = FileState.VALIDATING
        else:
            self.cksum.create()
            phase = FileState.CKSUM_CALC
        self.cksum.cmd.filesize = self.size
        return self._queue(phase, self.cksum.cmd, runlist, dependsOn)

    def Encrypt(self, target: str = "", runlist: str = "", dependsOn: str = "") -> str:
        self._accept()
        if self.encryption_scheme.mode is E_Mode.NONE:
            return dependsOn
        if self.encryption_scheme.state is not E_State.IDLE:
            raise RuntimeError("[ERROR] An encryption is still pending")

        self.encryption_scheme.encrypt(self.path.path, target)
        self.cryptPath = self.encryption_scheme.targetPath
        self.encryption_scheme.cmd.filesize = self.size
        return self._queue(FileState.ENCRYPT, self.encryption_scheme.cmd, runlist, dependsOn)

    def Write(self, tapeDrive: "TapeDrive", runlist: str = "", dependsOn: str = "") -> str:
        self._accept()
        source: str = self.path.path
        if self.encryption_scheme.mode is not E_Mode.NONE:
            if not self.cryptPath:
                raise RuntimeError("[ERROR] Encrypt() before Write()")
            source = self.cryptPath     # the tape gets the ciphertext

        # Built here (not via TapeDrive.write()): that one assumes a single write at a time
        cmd: Command = Command(
            "dd if=" + Command.quote(source) + " of=" + Command.quote(tapeDrive.path) + " " +
            "iflag=fullblock status=none bs=" + tapeDrive.blocksize,
            filesize=self.size)
        tapeDrive.tape.begin_of_tape = False
        return self._queue(FileState.WRITE, cmd, runlist, dependsOn, tape=tapeDrive.path)

    def Read(self, tapeDrive: "TapeDrive", target: str, runlist: str = "", dependsOn: str = "") -> str:
        self._accept()
        if self.encryption_scheme.mode is E_Mode.NONE:
            self.where = target         # this is already the plain file
        else:
            self.cryptPath = target     # Decrypt() takes it from here

        cmd: Command = Command(
            "dd if=" + Command.quote(tapeDrive.path) + " of=" + Command.quote(target) + " " +
            "iflag=fullblock status=none bs=" + tapeDrive.blocksize,
            filesize=self.size)
        return self._queue(FileState.READ, cmd, runlist, dependsOn, tape=tapeDrive.path)

    def Decrypt(self, target: str, runlist: str = "", dependsOn: str = "") -> str:
        self._accept()
        if self.encryption_scheme.mode is E_Mode.NONE:
            return dependsOn
        if not self.cryptPath:
            raise RuntimeError("[ERROR] Read() or Encrypt() before Decrypt()")
        if self.encryption_scheme.state is not E_State.IDLE:
            raise RuntimeError("[ERROR] An encryption is still pending")

        self.encryption_scheme.decrypt(self.cryptPath, target)
        self.where = target
        self.encryption_scheme.cmd.filesize = self.size
        return self._queue(FileState.DECRYPT, self.encryption_scheme.cmd, runlist, dependsOn)

# === FILE SYSTEM (instant, no Job) ============================================

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

    def remove(self) -> None:   # This removes FILE from filesystem
        try:
            os.remove(self.path.path)
        except PermissionError:
            self.state_msg.append("[ERROR] Deletion failed, permisson error occured '" + str(self.path) + "'")
            raise
        except Exception as e:
            self.state_msg.append("[ERROR] Deletion failed, unkown error" + str(self) + "   Exception: " + str(e))
            raise

        self.state = FileState.REMOVED
        self.size = -1

    def append(self, text: str):
        if self.state in {FileState.IDLE}:
            with open(self.path.path, "a") as file:
                file.write(text)

            self.readSize()

    def readSize(self) -> None:
        self.cmd.reset()
        self.cmd.cmd = "stat -c %s " + Command.quote(self.path.path)
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

# === STATE ====================================================================

    def _accept(self) -> None:
        if self.state in {FileState.INIT, FileState.ERROR, FileState.MISMATCH, FileState.REMOVED}:
            raise RuntimeError("[ERROR] File " + str(self.id) + " is " + self.state.name + ", no further phase possible")

    def _queue(self, phase: FileState, cmd: Command, runlist: str, dependsOn: str, tape: str = "") -> str:
        entry: str = Job.Add(cmd, tape=tape, dependsOn=dependsOn, runlist=runlist)
        self.entries.append((phase, entry))
        return entry

    def refresh(self) -> None:
        """Takes over the results of finished phases and derives the state from the Job entries."""
        if not self.entries or self._state is FileState.REMOVED or len(self.entries) == self._settled:
            return

        failed: bool = False
        mismatch: bool = False
        active: FileState | None = None
        queued: bool = False
        pending: bool = False

        for phase, entryId in self.entries:
            try:
                entry = Job.Get(entryId)
            except LookupError:
                continue    # Job was flushed

            if entry.state in Job.FINISHED:
                result: bool = self._takeOver(phase, entryId, entry.state is EntryState.COMPLETED)
                failed = failed or entry.state is EntryState.FAILED or not result
                mismatch = mismatch or (phase in {FileState.CKSUM_CALC, FileState.VALIDATING}
                                        and self._cksum.state is ChecksumState.MISMATCH)
            elif entry.state is EntryState.RUNNING:
                active = active or phase
                pending = True
            else:
                queued = True
                pending = True

        if not pending:
            self._settled = len(self.entries)   # nothing can change until a new phase is added

        if failed:
            self._state = FileState.ERROR
        elif mismatch:
            self._state = FileState.MISMATCH
        elif active:
            self._state = active
        elif queued:
            self._state = FileState.QUEUED
        else:
            self._state = FileState.IDLE

    def _takeOver(self, phase: FileState, entryId: str, completed: bool) -> bool:
        """Reads the result of a finished phase once. Returns False if the phase has failed."""
        first: bool = entryId not in self._taken
        self._taken.add(entryId)

        if phase in {FileState.CKSUM_CALC, FileState.VALIDATING}:
            self._cksum._status()
            if self._cksum.state is ChecksumState.MISMATCH and first:
                self.state_msg.append("[ERROR] Checksum mismatch!")
            ok: bool = completed and self._cksum.state is not ChecksumState.ERROR
        elif phase in {FileState.ENCRYPT, FileState.DECRYPT}:
            self._encryption.refresh()
            ok = completed and self._encryption.state is not E_State.ERROR
        else:
            ok = completed

        if not ok and first:
            self.state_msg.append("[ERROR] " + phase.name + " failed or was not run")
        return ok

    def _asdict(self) -> dict:
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

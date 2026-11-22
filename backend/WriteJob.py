import json
import os
import uuid
from typing import List

from backend.Checksum import ChecksumType
from backend.Command import Command
from backend.Encryption import E_Mode
from backend.Folder import Folder
from backend.Job import EntryState, Job
from backend.Spool import Spool
from backend.TableOfContent import TableOfContent, TOC_Header, TOC_State
from backend.TapeDrive import TapeDrive

class WriteJob:

    """
    The complete run list of one write request, queued in one go:

        all checksums -> rewind -> first TOC -> per file: encrypt, write -> last TOC -> rewind [-> eject]

    The order on the tape is the order of the queue (see Job). The drive stays idle until it could,
    in theory, write both TOCs: that is when the checksum of every file is known. The first TOC is
    made then (state IDLE) and the last one just before it is written (state COMPLETE, or FAILED if
    a step failed). Both hold the same plan, the same keys and the same checksums; only the state
    and the log of the commands differ. A tape cannot be changed in place, so the first TOC could
    never be completed afterwards. If a checksum fails the tape is not touched at all. After a later
    failure no further file is written, but the last TOC and the rewind still run. The eject only
    runs if the job succeeded and `eject=True`, it is off by default.

        >>> job = WriteJob("/data/in", td, "passphrase", "/path/to/storage")
        >>> job.queue()
        >>> job.wait()
        >>> print(job)

    | `WriteJob.`        | Description                                                          |
    |--------------------|----------------------------------------------------------------------|
    | `queue()`          | Checks the request, creates the spool, queues everything, returns the ids |
    | `wait(timeout)`    | Blocks until everything is finished, False on timeout                |
    | `state`            | `NEW`, `RUNNING`, `COMPLETED` or `FAILED`                            |
    | `folder`, `toc`    | what is written; `folder.files[n].state` is the result per file      |

    `queue()` refuses the request up front if the folder is empty, the tape is missing or write
    protected, the files do not fit the native capacity of the tape, or the spool mount has less
    free space than the input (the spool holds all encrypted files until the end).
    `tocDir` is where a copy of the last TOC is kept (optional).

    Without a passphrase the request is refused ("Passphrase for encryption required"), unless
    `unencrypted=True`: then the TOC removes all encryption (see `TableOfContent.removeEncryption()`),
    nothing is encrypted and the TOC is not sealed. `unencrypted` and a passphrase exclude each
    other, `encryption` is ignored with `unencrypted`.
    """

    def __init__(self, inputDir: str, tapeDrive: TapeDrive, passphrase: str, spoolMount: str, tocDir: str = "",
                 checksum: ChecksumType = ChecksumType.SHA256, encryption: E_Mode = E_Mode.AES256CBC,
                 eject: bool = False, unencrypted: bool = False):
        if unencrypted and passphrase:
            raise ValueError("A passphrase and unencrypted exclude each other")
        if not unencrypted and not passphrase:
            raise ValueError("Passphrase for encryption required")
        if not unencrypted and encryption is E_Mode.NONE:
            raise ValueError("No encryption needs unencrypted=True")

        self.drive: TapeDrive = tapeDrive
        self.passphrase: str = passphrase
        self.tocDir: str = tocDir
        self.eject: bool = eject
        self.runlist: str = str(uuid.uuid4())
        self.entries: List[str] = []
        self.firstToc: str = ""         # entry id of the write of the first TOC

        self.folder: Folder = Folder(inputDir, checksum, encryption)
        self.toc: TableOfContent = TableOfContent(self.folder, TOC_Header(tapeDrive, Job.limit))
        if unencrypted:
            self.toc.removeEncryption()
        self.spool: Spool = Spool(spoolMount, self.toc.header.fingerprint)

    def _check(self) -> None:
        total: int = sum(f.size for f in self.folder.files)
        if not self.folder.files:
            raise ValueError("No files in " + self.folder.path)
        self.drive.requireTape()
        tape = self.drive.tape
        if tape.write_protect:
            raise ValueError("The tape is write protected")
        if tape.native_capacity and total > tape.native_capacity:
            raise ValueError("The files (" + str(total) + " bytes) do not fit the tape (" + str(tape.native_capacity) + " bytes)")
        if self.folder.encMode is not E_Mode.NONE and total > self.spool.mount.avail:
            raise ValueError("The spool mount has " + str(self.spool.mount.avail) + " bytes free, the input is " + str(total) + " bytes")

    def _write(self, name: str, text: str) -> str:
        path: str = os.path.join(self.spool.path, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def _firstToc(self) -> None:
        """Runs right before the first TOC is written, when every checksum is known."""
        self._write("toc_start.json", self.toc.seal(self.passphrase))

    def _lastToc(self) -> None:
        """Runs right before the last TOC is written, when the results of all files are known."""
        if Job.Get(self.firstToc).state is not EntryState.COMPLETED:
            raise RuntimeError("The first TOC is not on the tape, the tape was not touched")
        self.toc.header.state = TOC_State.FAILED if Job.Failed(self.runlist) else TOC_State.COMPLETE
        self._write("toc_end.json", self.toc.seal(self.passphrase))
        if self.tocDir:
            self.toc.store(self.tocDir)

    def queue(self) -> List[str]:
        if self.entries:
            raise RuntimeError("This job is queued already")
        self._check()

        r: str = self.runlist
        self.spool.create()

        checksums: List[str] = self.folder.queueChecksums(r, self.drive.id)
        known: str = Job.Add(Command("true"), runlist=r, waitFor=[c for c in checksums if c], drive=self.drive.id)      # all checksums are known

        self.drive.Rewind(runlist=r, dependsOn=known)
        self.firstToc = self.drive.Write(os.path.join(self.spool.path, "toc_start.json"), runlist=r, prepare=self._firstToc,
                                          blocksize=self.drive.tocBlock())
        self.folder.queueWrite(self.drive, r, self.spool, checksums)
        self.drive.Write(os.path.join(self.spool.path, "toc_end.json"), runlist=r, always=True, prepare=self._lastToc,
                         blocksize=self.drive.tocBlock())
        rewound: str = self.drive.Rewind(runlist=r, always=True)
        if self.eject:
            self.drive.Eject(runlist=r)                 # only after success: a failed job aborts it
        Job.Add(Command("true"), runlist=r, dependsOn=rewound, always=True, prepare=self.spool.remove, drive=self.drive.id)

        with Job.lock:
            self.entries = [e.id for e in Job.queue if e.runlist == r]
        return self.entries

    def wait(self, timeoutSec: float = 0) -> bool:
        return Job.Wait(self.entries, timeoutSec)

    @property
    def state(self) -> str:
        if not self.entries:
            return "NEW"
        states = [Job.Get(e).state for e in self.entries]
        if any(s not in Job.FINISHED for s in states):
            return "RUNNING"
        return "COMPLETED" if all(s is EntryState.COMPLETED for s in states) else "FAILED"

    def _asdict(self) -> dict:
        return {
            "runlist": self.runlist,
            "state": self.state,
            "fingerprint": self.toc.header.fingerprint,
            "spool": self.spool.path,
            "drive": self.drive.id,
            "files": [{"id": f.id, "path": f.path.relPath, "state": f.state.name} for f in self.folder.files],
        }

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

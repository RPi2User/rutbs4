import glob
import json
import os
import uuid
from datetime import datetime
from typing import List

from backend.Command import Command
from backend.Encryption import E_Mode
from backend.File import File, FileState
from backend.Job import EntryState, Job
from backend.Mount import Mount
from backend.Spool import Spool
from backend.Tape import E_Tape
from backend.TableOfContent import TableOfContent, TOC_State
from backend.TapeDrive import TapeDrive

class ReadJob:

    """
    The complete run list of one restore request, in two steps because the operator is asked for
    the passphrase after seeing which tape is loaded:

        open():   rewind -> read the first TOC -> to the end -> read the last TOC -> rewind
        queue():  skip the first TOC -> per file: read, decrypt, checksum -> rewind

        >>> job = ReadJob(td, "/data/restore", "/stornvme", tocDir="/data/tocs")
        >>> job.open()                       # the clear text headers: which tape is this?
        >>> job.queue("passphrase")          # TOC_WrongPassphrase: nothing was queued, ask again
        >>> job.wait()
        >>> print(job)

    | `ReadJob.`         | Description                                                          |
    |--------------------|----------------------------------------------------------------------|
    | `open()`           | Reads both TOCs from the tape, returns their headers (no passphrase) |
    | `queue(passphrase)`| Opens and compares the TOCs, queues the restore, returns the ids (a plain tape needs no passphrase) |
    | `wait(timeout)`    | Blocks until everything is finished, False on timeout                |
    | `state`            | `NEW`, `OPEN`, `RUNNING`, `COMPLETED` or `FAILED`                    |
    | `messages`         | warnings, for example that the last TOC came from the TOC directory  |

    The last TOC is reached without reading at the end of the data (that would lock the kernel
    driver, see TapeDrive): to the end, two file marks back, one forward. It holds the checksums,
    the first one is only the plan. A tape without a last TOC is not complete; if `tocDir` holds
    the copy that the write job made, that one is used and a warning says so.

    `queue()` refuses the request if the two TOCs disagree about the plan (see
    `TableOfContent.differences()`), if the job that wrote the tape failed, if a file to restore
    exists already, or if the spool or the target mount is too small. The files go to
    `<targetDir>/<relPath>`. With `tocDir` both TOCs are also kept there in clear text
    (`*.first.plain.json`, `*.last.plain.json`): **they contain the keys of every file.**
    A file is only good if `File.state` is `IDLE` after the job, `MISMATCH` means the checksum differs.
    """

    TOC_BLOCKS: int = 4096      # a TOC is read at most that many blocks long (1 GiB of 256K blocks)

    def __init__(self, tapeDrive: TapeDrive, targetDir: str, spoolMount: str, tocDir: str = ""):
        self.drive: TapeDrive = tapeDrive
        self.targetDir: str = targetDir
        self.tocDir: str = tocDir
        self.runlist: str = str(uuid.uuid4())
        self.entries: List[str] = []
        self.messages: List[str] = []
        self.files: List[File] = []

        self.spool: Spool = Spool(spoolMount, self.runlist)
        self._first: str = ""       # the sealed TOCs as read from the tape
        self._last: str = ""
        self._opened: bool = False

    # === STEP 1: THE TOCS ====================================================

    def _failure(self, entries: List[str]) -> str:
        for entryId in entries:
            entry = Job.Get(entryId)
            if entry.state is EntryState.FAILED and not entry.always:
                return entry.error or " ".join(entry.command.stderr) or ("exit code " + str(entry.command.exitCode) + ": " + entry.command.cmd)
        return "unknown"

    @staticmethod
    def _text(path: str) -> str:
        try:
            with open(path) as f:
                text: str = f.read()
            TableOfContent.readHeader(text)
            return text
        except (OSError, ValueError):      # not there, not text, not JSON, not a rutbs TOC
            return ""

    def open(self) -> dict:
        if self._opened:
            raise RuntimeError("This job is opened already")
        if self.drive.tape.state is E_Tape.NO_TAPE:
            raise ValueError("No tape in the drive")

        d: TapeDrive = self.drive
        r: str = self.runlist
        self.spool.create()
        first: str = os.path.join(self.spool.path, "toc_start.json")
        last: str = os.path.join(self.spool.path, "toc_end.json")

        ids: List[str] = [
            d.Rewind(runlist=r),
            d.Read(first, runlist=r, count=self.TOC_BLOCKS),
            d.SpaceEnd(runlist=r),
            d.Space(-2, runlist=r),         # before the file mark that ends the last file
            d.Space(1, runlist=r),          # behind it: the begin of the last TOC
            d.Read(last, runlist=r, count=self.TOC_BLOCKS),
            d.Rewind(runlist=r, always=True),
        ]
        Job.Wait(ids)
        self._first = self._text(first)
        self._last = self._text(last)
        self.spool.remove()                 # the TOCs are in memory now

        if not self._first:
            why: str = self._failure(ids) if Job.Failed(r) else "the first tape file is not a rutbs TOC"
            raise RuntimeError("Cannot read the first TOC: " + why)
        self._opened = True

        header: dict = {"first": TableOfContent.readHeader(self._first), "last": None}
        if self._last:
            header["last"] = TableOfContent.readHeader(self._last)
        else:
            self.messages.append("[WARNING] The tape has no last TOC, it is not complete")
        return header

    # === STEP 2: THE FILES ===================================================

    def _fromDirectory(self, fingerprint: str) -> str:
        if not self.tocDir:
            return ""
        copies: List[str] = sorted(glob.glob(os.path.join(self.tocDir, "*_" + fingerprint + ".json")))
        if not copies:
            return ""
        text: str = self._text(copies[-1])
        if text:
            self.messages.append("[WARNING] The last TOC is the copy " + copies[-1] + ", not the one on the tape")
        return text

    def _keep(self, first: dict, last: dict) -> None:
        """Both TOCs in clear text, readable for the owner only."""
        header: dict = last["header"]
        stamp: str = datetime.fromisoformat(header["created"]).strftime("%Y%m%d_%H%M%S")
        for name, toc in (("first", first), ("last", last)):
            path: str = os.path.join(self.tocDir, stamp + "_" + header["fingerprint"] + "." + name + ".plain.json")
            fd: int = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(toc, f, indent=2)

    def _check(self, entries: List[dict]) -> None:
        total: int = sum(e["size"] for e in entries)
        for e in entries:
            if os.path.lexists(os.path.join(self.targetDir, e["path"]["relPath"])):
                raise ValueError("'" + e["path"]["relPath"] + "' exists already in " + self.targetDir)

        target: Mount | None = Mount.of(self.targetDir)
        if target is not None and total > target.avail:
            raise ValueError("The target has " + str(target.avail) + " bytes free, the files are " + str(total) + " bytes")
        if any(e["encryption"]["mode"] != E_Mode.NONE.name for e in entries) and total > self.spool.mount.avail:
            raise ValueError("The spool mount has " + str(self.spool.mount.avail) + " bytes free, the files are " + str(total) + " bytes")

    def queue(self, passphrase: str = "") -> List[str]:
        if self.entries:
            raise RuntimeError("This job is queued already")
        if not self._opened:
            raise RuntimeError("open() the tape first")

        first: dict = TableOfContent.open(self._first, passphrase)      # TOC_WrongPassphrase: nothing is queued
        text: str = self._last or self._fromDirectory(first["header"]["fingerprint"])
        if not text:
            raise ValueError("There is no last TOC, neither on the tape nor in the TOC directory: the tape is not complete")
        last: dict = TableOfContent.open(text, passphrase)

        differences: List[str] = TableOfContent.differences(first, last)
        if differences:
            raise ValueError("The first and the last TOC disagree:\n  " + "\n  ".join(differences))
        if last["header"]["state"] == TOC_State.FAILED.name:
            raise ValueError("The job that wrote this tape failed")

        entries: List[dict] = last["body"]["folder"]["files"]
        self._check(entries)
        if self.tocDir:
            self._keep(first, last)

        d: TapeDrive = self.drive
        r: str = self.runlist
        self.spool.create()
        self.files = [File.Restore(e, self.targetDir) for e in entries]

        d.Space(1, runlist=r)                   # the tape is at its begin: skip the first TOC
        for f in self.files:
            encrypted: bool = f.encryption_scheme.mode is not E_Mode.NONE
            step: str = f.Read(d, self.spool.file(f.id) if encrypted else f.path.path, runlist=r)
            step = f.Decrypt(f.path.path, runlist=r, dependsOn=step, drive=d.id)
            f.Validate(runlist=r, dependsOn=step, drive=d.id)
        rewound: str = d.Rewind(runlist=r, always=True)
        Job.Add(Command("true"), runlist=r, dependsOn=rewound, always=True, prepare=self.spool.remove, drive=d.id)

        with Job.lock:
            self.entries = [e.id for e in Job.queue if e.runlist == r]
        return self.entries

    def wait(self, timeoutSec: float = 0) -> bool:
        return Job.Wait(self.entries, timeoutSec)

    @property
    def state(self) -> str:
        if not self.entries:
            return "OPEN" if self._opened else "NEW"
        if any(Job.Get(e).state not in Job.FINISHED for e in self.entries):
            return "RUNNING"
        good: bool = all(Job.Get(e).state is EntryState.COMPLETED for e in self.entries)
        return "COMPLETED" if good and all(f.state is FileState.IDLE for f in self.files) else "FAILED"

    def _asdict(self) -> dict:
        return {
            "runlist": self.runlist,
            "state": self.state,
            "drive": self.drive.id,
            "target": self.targetDir,
            "messages": self.messages,
            "files": [{"id": f.id, "path": f.path.relPath, "state": f.state.name, "messages": f.state_msg} for f in self.files],
        }

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

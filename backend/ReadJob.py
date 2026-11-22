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
from backend.TableOfContent import TableOfContent, TOC_State
from backend.TapeDrive import TapeDrive

class ReadJob:

    """
    The complete run list of one restore request, in two steps because the operator is asked for
    the passphrase after seeing which tape is loaded:

        open():   rewind -> read the first TOC -> rewind
        queue():  rewind -> read the first TOC -> per file: read, decrypt, checksum -> read the last TOC -> rewind

        >>> job = ReadJob(td, "/data/restore", "/stornvme", tocDir="/data/tocs")
        >>> job.open()                       # the clear text header: which tape is this?
        >>> job.queue("passphrase")          # TOC_WrongPassphrase: nothing was queued, ask again
        >>> job.wait()
        >>> print(job)

    | `ReadJob.`         | Description                                                          |
    |--------------------|----------------------------------------------------------------------|
    | `open()`           | Reads the first TOC from the tape, returns its header (no passphrase) |
    | `queue(passphrase)`| Opens the first TOC, queues the restore, returns the ids (a plain tape needs no passphrase) |
    | `wait(timeout)`    | Blocks until everything is finished, False on timeout                |
    | `state`            | `NEW`, `OPEN`, `RUNNING`, `COMPLETED` or `FAILED`                    |
    | `messages`         | what went wrong, for example that the tape is not valid              |

    The tape is only read from its begin to its end, nothing is skipped or seeked. The first TOC says how many
    files follow, so nothing is ever read behind the last TOC (that would lock the kernel driver, see
    TapeDrive).

    **The last TOC decides whether the files were restored.** It is read last and has to agree with the first
    one about the plan (see `TableOfContent.differences()`) and to be `COMPLETE`. Without it, or if it
    disagrees, the tape is not valid: the job is `FAILED`, whatever the files look like. There is no other
    source for it. The first TOC only says which tape it is, and whether something happened to it already (a
    `FAILED` one is refused at once).

    `queue()` refuses the request if a file to restore exists already, or if the spool or the target mount
    is too small. The files go to `<targetDir>/<relPath>`. With `tocDir` both TOCs are kept there in clear text
    when the job is good (`*.first.plain.json`, `*.last.plain.json`): **they contain the keys of every file.**
    A file is only good if the job is `COMPLETED` and `File.state` is `IDLE`, `MISMATCH` means the checksum differs.
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
        self._first: str = ""       # the first TOC as read from the tape
        self._plan: dict = {}       # the same one, opened
        self._passphrase: str = ""  # needed again for the last TOC, dropped afterwards
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
        self.drive.requireTape()

        d: TapeDrive = self.drive
        r: str = self.runlist
        self.spool.create()
        first: str = os.path.join(self.spool.path, "toc_start.json")

        ids: List[str] = [
            d.Rewind(runlist=r),
            d.Read(first, runlist=r, count=self.TOC_BLOCKS),
            d.Rewind(runlist=r, always=True),
        ]
        Job.Wait(ids)
        self._first = self._text(first)
        self.spool.remove()                 # the TOC is in memory now

        if not self._first:
            why: str = self._failure(ids) if Job.Failed(r) else "the first tape file is not a rutbs TOC"
            raise RuntimeError("Cannot read the first TOC: " + why)
        self._opened = True
        return TableOfContent.readHeader(self._first)

    # === STEP 2: THE FILES ===================================================

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
            File.encryptionOf(e)            # ValueError: a key that is none, nothing is created in the target
            if os.path.lexists(os.path.join(self.targetDir, e["path"]["relPath"])):
                raise ValueError("'" + e["path"]["relPath"] + "' exists already in " + self.targetDir)

        target: Mount | None = Mount.of(self.targetDir)
        if target is not None and total > target.avail:
            raise ValueError("The target has " + str(target.avail) + " bytes free, the files are " + str(total) + " bytes")
        if any(e["encryption"]["mode"] != E_Mode.NONE.name for e in entries) and total > self.spool.mount.avail:
            raise ValueError("The spool mount has " + str(self.spool.mount.avail) + " bytes free, the files are " + str(total) + " bytes")

    def _lastToc(self) -> None:
        """Runs after the last TOC was read and decides: only with a good one the files were restored."""
        try:
            text: str = self._text(self._lastPath)
            if not text:
                raise RuntimeError("the last tape file is not a rutbs TOC")
            last: dict = TableOfContent.open(text, self._passphrase)
            differences: List[str] = TableOfContent.differences(self._plan, last)
            if differences:
                raise RuntimeError("the first and the last TOC disagree: " + "; ".join(differences))
            if last["header"]["state"] != TOC_State.COMPLETE.name:
                raise RuntimeError("the job that wrote this tape did not complete")
            if self.tocDir:
                self._keep(self._plan, last)
        except Exception as ex:
            raise RuntimeError("The tape is not valid: " + str(ex)) from ex
        finally:
            self._passphrase = ""

    def _closing(self) -> None:
        self._passphrase = ""
        self.spool.remove()

    def queue(self, passphrase: str = "") -> List[str]:
        if self.entries:
            raise RuntimeError("This job is queued already")
        if not self._opened:
            raise RuntimeError("open() the tape first")

        plan: dict = TableOfContent.open(self._first, passphrase)       # TOC_WrongPassphrase: nothing is queued
        if plan["header"]["state"] == TOC_State.FAILED.name:
            raise ValueError("The job that wrote this tape failed, the tape is not valid")
        blocksize: str = plan["header"]["blocksize"]
        TapeDrive.blockBytes(blocksize)                                 # ValueError, it goes into a command

        entries: List[dict] = plan["body"]["folder"]["files"]
        self._check(entries)
        files: List[File] = [File.Restore(e, self.targetDir) for e in entries]     # ValueError: no spool yet

        d: TapeDrive = self.drive
        r: str = self.runlist
        self._plan = plan
        self._passphrase = passphrase
        self.spool.create()
        self._lastPath: str = os.path.join(self.spool.path, "toc_end.json")
        self.files = files

        d.Rewind(runlist=r)
        d.Read(os.path.join(self.spool.path, "toc_start.json"), runlist=r, count=self.TOC_BLOCKS)      # known already, read past it
        taken: List[str] = []
        for f in self.files:
            encrypted: bool = f.encryption_scheme.mode is not E_Mode.NONE
            step = f.Read(d, self.spool.file(f.id) if encrypted else f.path.path, runlist=r, blocksize=blocksize)
            step = f.Decrypt(f.path.path, runlist=r, dependsOn=step, drive=d.id)
            if step:                            # an empty plain file has no step at all
                taken.append(step)
            f.Validate(runlist=r, dependsOn=step, drive=d.id)
        step = d.Read(self._lastPath, runlist=r, count=self.TOC_BLOCKS)
        self.lastToc: str = Job.Add(Command("true"), runlist=r, dependsOn=step, prepare=self._lastToc, drive=d.id)
        rewound: str = d.Rewind(runlist=r, always=True)
        # The spool may only go when the last TOC was looked at and every file was taken from it
        Job.Add(Command("true"), runlist=r, waitFor=[rewound, self.lastToc] + taken, always=True, prepare=self._closing, drive=d.id)

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
        state: str = self.state
        why: List[str] = [self._failure(self.entries)] if state == "FAILED" and Job.Failed(self.runlist) else []
        if state == "FAILED":
            why.append("The files in the target must not be trusted")
        return {
            "runlist": self.runlist,
            "state": state,
            "drive": self.drive.id,
            "target": self.targetDir,
            "messages": self.messages + why,
            "files": [{"id": f.id, "path": f.path.relPath, "state": f.state.name, "messages": f.state_msg} for f in self.files],
        }

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

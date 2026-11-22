from enum import Enum
import json
import os
import threading
import time
import uuid
from typing import Callable, List, Optional

from backend.Command import Command

class EntryState(Enum):
    KILLED = -2     # urgent Entry: deadline exceeded, the process was killed (or given up)
    FAILED = -1
    WAITING_FOR_PARENT = 0
    READY4EXEC = 1
    RUNNING = 2
    COMPLETED = 3

class Entry():

    """
    #### === ENTRY ============================================================

    Entry.__init__(command: Command, tape: str = "", dependsOn: str = "", runlist: str = "", always: bool = False,
                   prepare: Callable[[], None] | None = None, waitFor: List[str] | None = None,
                   startAfterCreate: bool = False, deadlineMs: int = 0, drive: str = ""):
    - Requires
        - A Command that has not been started yet
    - Supports
        - tape:      id of the drive if this Command uses it (scheduling: one at a time, in order)
        - drive:     id of the drive (its wwid) whose request the Entry belongs to, also for checksum,
                     encryption and closing steps. A tape Entry belongs to its own drive. `""` = no drive
        - dependsOn: id of the parent Entry, which must be COMPLETED first
        - waitFor:   ids of further Entries that must be COMPLETED first (a barrier: "all checksums are done")
        - runlist:   id of the request this Entry belongs to (e.g. one tape write)
        - always:    closing step, runs even if its runlist was aborted
        - prepare:   called right before the Command starts, e.g. to write the file the Command
                     reads. If it raises, the Entry FAILED and the Command never ran
        - startAfterCreate: the constructor starts the Command as its last step (urgent Entry,
                     see `Job.Add(urgent=True)`); the Entry is RUNNING from the first moment
        - deadlineMs: urgent Entry only: killed after this time, state KILLED

    | Var              | Type         | Description                                     |
    |------------------|--------------|-------------------------------------------------|
    | `self.id`        | `str`        | UUID, returned by `Job.Add()`                   |
    | `self.command`   | `Command`    | The work itself                                 |
    | `self.tape`      | `str`        | Drive id, `""` for CPU/Disk work                |
    | `self.drive`     | `str`        | Drive id of the request, see `drive` above      |
    | `self.dependsOn` | `str`        | Parent id, `""` if there is no parent           |
    | `self.waitFor`   | `List[str]`  | Further ids to wait for, `[]` if none           |
    | `self.runlist`   | `str`        | Request id, `""` if the Entry stands alone      |
    | `self.always`    | `bool`       | `True`: is not aborted with its runlist         |
    | `self.prepare`   | `callable`   | Runs just before the start, `None` if unused    |
    | `self.error`     | `str`        | Why `prepare` failed, `""` otherwise            |
    | `self.urgent`    | `bool`       | Started at once, outside the queue and the slots |
    | `self.deadlineMs`| `int`        | Urgent: time until the kill, `0` for queued work |
    | `self.state`     | `EntryState` | See `Job` for the state flow                    |
    """

    def __init__(self, command: Command, tape: str = "", dependsOn: str = "", runlist: str = "", always: bool = False,
                 prepare: Callable[[], None] | None = None, waitFor: List[str] | None = None,
                 startAfterCreate: bool = False, deadlineMs: int = 0, drive: str = "") -> None:
        self.id: str = str(uuid.uuid4())
        self.prepare: Callable[[], None] | None = prepare
        self.error: str = ""
        self.command: Command = command
        self.tape: str = tape
        self.drive: str = drive or tape
        self.dependsOn: str = dependsOn
        self.waitFor: List[str] = list(waitFor or [])
        self.runlist: str = runlist
        self.always: bool = always
        self.state: EntryState = EntryState.WAITING_FOR_PARENT if dependsOn or self.waitFor else EntryState.READY4EXEC
        self.urgent: bool = startAfterCreate
        self.deadlineMs: int = deadlineMs
        self.deadline: float = 0.0              # time.monotonic() of the kill, urgent only

        if startAfterCreate:                    # LAST step: everything else is set when the process runs
            self.command.start()
            self.deadline = time.monotonic() + deadlineMs / 1000
            self.state = EntryState.RUNNING

    @property
    def parents(self) -> List[str]:
        return ([self.dependsOn] if self.dependsOn else []) + self.waitFor

    def _asdict(self) -> dict:
        _out: dict = {
            "id": self.id,
            "state": self.state.name,
            "tape": self.tape,
            "drive": self.drive,
            "dependsOn": self.dependsOn,
            "waitFor": self.waitFor,
            "runlist": self.runlist,
            "always": self.always,
            "urgent": self.urgent,
            "deadlineMs": self.deadlineMs,
            "error": self.error,
            "command": self.command._asdict(),
        }
        return {"Entry": _out}

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

class JobState(Enum):
    EMPTY = -1
    IDLE = 0
    WORKING = 1

class Job():

    """
    #### === JOB ==============================================================

    Job schedules Commands. There is ONE queue for the whole host, so the
    thread limit holds no matter how many requests are queued.
    Each Entry may depend on ONE parent Entry (`dependsOn`) and may in addition wait for a list of
    others (`waitFor`, e.g. an Entry that starts when all checksums are done). A closing step (`always`)
    waits for its `waitFor` to end, however they ended (e.g. to remove the spool when nobody reads it any more).
    Parents must be added before their children, so the queue is always in
    dependency order and a single pass over it resolves the whole tree.

    Example (write a file to tape):
        c = Job.Add(Command("sha256sum a"))
        e = Job.Add(Command("encrypt a"),         dependsOn=c)
        w = Job.Add(Command("dd ... of=/dev/nst0"), tape="/dev/nst0", dependsOn=e)
        ...
        Job.Work()

    State flow of an Entry:
        WAITING_FOR_PARENT --all parents COMPLETED--> READY4EXEC --> RUNNING --> COMPLETED
                           --a parent FAILED-------> FAILED                 --> FAILED (exitCode != 0)

    Runlist:
        All Entries of one request (e.g. "write this folder to that tape") share a runlist id.
        If one of them fails, the request is aborted: every Entry of the runlist that has
        not been started yet fails as well, running ones finish. Entries added with
        always=True are closing steps (final TOC, rewind) and still run.
        Other runlists are not affected.

    Urgent (system commands):
        Small requests (a few random bytes, `stat`, `findmnt`, a SCSI query) must not wait for a slot.
        `Job.Add(cmd, urgent=True)` starts the Command at once, in the caller's thread, outside the queue
        and outside `Job.limit`; the Entry lives in its own list (`Job.urgent`, the last
        `URGENT_KEEP` finished ones are kept). Whoever looks at it (`Job.Get()`, `Job.Refresh()`)
        enforces the deadline: SIGTERM, SIGKILL, then the Entry is KILLED, a process that
        does not die is given up. `Job.Run(cmd)` is Add + wait for the result.
        An urgent Entry takes no part in dependencies, runlists, drives or `prepare`, so it can be
        used from constructors and from `prepare` hooks (they run under the Job lock).
        Not for the regular case: whatever is needed often belongs in a small list that is
        refreshed periodically. Never rewind, eject, dd, checksum or encryption.

    Scheduling (every tick, in this order):
        1. Tape Entries          -> one Entry per drive, strictly in the order they were added,
                                    so the order on tape is known before anything is written
        2. Entries feeding tape  -> e.g. checksum/encryption before a tape write
        3. Everything else       -> e.g. decrypt/verify after the tape
        Same priority: first come, first serve. CPU work is limited by `Job.limit`.

    | `Job.`             | Description                                              |
    |--------------------|----------------------------------------------------------|
    | `Job.Add()`        | Adds a Command, returns the Entry id (`urgent=True`: starts it now) |
    | `Job.Run()`        | Urgent Command, blocks, returns the finished Command     |
    | `Job.Failed()`     | True if an Entry of a runlist failed (closing steps excluded) |
    | `Job.Get()`        | Returns the Entry of an id, raises LookupError           |
    | `Job.Registry()`   | Returns all Entries as dict                              |
    | `Job.Flush()`      | Kills & removes all, or (killRunning=False) removes done; `drive=` limits it to one drive |
    | `Job.Refresh()`    | One scheduler tick: update states, start Entries         |
    | `Job.Wait()`       | Blocks until the given Entries are COMPLETED or FAILED   |
    | `Job.Work()`       | Starts the JobScheduler thread (calls Refresh)           |
    | `Job.Stop()`       | Stops the JobScheduler thread                            |
    """

    DEFAULT_THREADLIMIT: int = os.cpu_count() or 1
    FINISHED = {EntryState.COMPLETED, EntryState.FAILED, EntryState.KILLED}
    DEFAULT_DEADLINE_MS: int = 2000             # urgent Entries; `find` of a folder gets 60 s from its caller
    URGENT_KEEP: int = 200                      # finished urgent Entries that stay in the registry

    state: JobState = JobState.EMPTY
    queue: List[Entry] = []
    urgent: List[Entry] = []                    # started by Add(urgent=True), never part of the queue
    limit: int = DEFAULT_THREADLIMIT            # max. parallel CPU/Disk Entries
    lock: threading.RLock = threading.RLock()   # Add() and the scheduler thread share the queue
    scheduler: Optional["JobScheduler"] = None

# --- PUBLIC FUNCTIONS ----------------------------------------------------------------------------

    @staticmethod
    def Add(cmd: Command, tape: str = "", dependsOn: str = "", runlist: str = "", always: bool = False,
            prepare: Callable[[], None] | None = None, waitFor: List[str] | None = None,
            urgent: bool = False, deadlineMs: int = DEFAULT_DEADLINE_MS, drive: str = "") -> str:
        with Job.lock:
            if any(e.command is cmd for e in Job.queue + Job.urgent):
                raise ValueError("ERROR: Command already queued, create a new Command object")

            if urgent:
                if tape or dependsOn or runlist or always or prepare or waitFor:
                    raise ValueError("ERROR: An urgent Entry stands alone: no tape, parent, runlist or prepare")
                _u: Entry = Entry(cmd, startAfterCreate=True, deadlineMs=deadlineMs, drive=drive)    # starts the Command
                Job.urgent.append(_u)
                Job._trimUrgent()
                return _u.id

            for parent in ([dependsOn] if dependsOn else []) + list(waitFor or []):
                Job.Get(parent)         # raises LookupError if the parent is unknown

            _e: Entry = Entry(cmd, tape, dependsOn, runlist, always, prepare, waitFor, drive=drive)
            Job.queue.append(_e)
            Job._updateStates()         # parent might already be COMPLETED
            Job._updateJobState()
            return _e.id

    @staticmethod
    def Run(cmd: Command, deadlineMs: int = DEFAULT_DEADLINE_MS) -> Command:
        """
        An urgent Entry and the wait for it. Returns the finished Command: check its `exitCode`
        (a killed Command has the exit code of the signal, or -1 if it could not be killed;
        `status_msg` says why). Does not drive the queue, so it is safe inside `prepare` hooks.
        """
        _id: str = Job.Add(cmd, urgent=True, deadlineMs=deadlineMs)
        while Job.Get(_id).state not in Job.FINISHED:
            time.sleep(0.002)
        return cmd

    @staticmethod
    def Failed(runlist: str) -> bool:
        """True if an Entry of the runlist failed. Closing steps (always=True) do not count."""
        with Job.lock:
            return any(e.runlist == runlist and e.state is EntryState.FAILED and not e.always for e in Job.queue)

    @staticmethod
    def Get(entryId: str) -> Entry:
        with Job.lock:
            for entry in Job.queue + Job.urgent:
                if entry.id == entryId:
                    if entry.urgent:
                        Job._checkUrgent(entry)     # whoever looks drives the deadline
                    return entry
        raise LookupError("Entry not found: " + entryId)

    @staticmethod
    def Registry(drive: str = "") -> dict:
        """All Entries as dict; with `drive` only those of that drive."""
        with Job.lock:
            return {entry.id: entry._asdict() for entry in Job.queue + Job.urgent if not drive or entry.drive == drive}

    @staticmethod
    def Flush(killRunning: bool = True, drive: str = "") -> None:
        """
        Removes Entries of both lists: all of them, or with `drive` only those of that drive (the
        request of another drive keeps running). killRunning=True kills the running ones first,
        False removes the finished ones only.
        """
        with Job.lock:
            mine = lambda e: not drive or e.drive == drive
            if killRunning:
                for entry in Job.queue + Job.urgent:
                    if mine(entry) and entry.state is EntryState.RUNNING:
                        entry.command.kill()
                Job.queue[:] = [e for e in Job.queue if not mine(e)]
                Job.urgent[:] = [e for e in Job.urgent if not mine(e)]
            else:
                Job._updateStates()     # a WAITING child never loses its unfinished parent
                Job.queue[:] = [e for e in Job.queue if not (mine(e) and e.state in Job.FINISHED)]
                Job.urgent[:] = [e for e in Job.urgent if not (mine(e) and e.state in Job.FINISHED)]
            Job._updateJobState()

    @staticmethod
    def Refresh() -> None:
        with Job.lock:
            for entry in Job.urgent:
                Job._checkUrgent(entry)
            Job._updateStates()
            Job._startEntries()
            Job._updateJobState()

    @staticmethod
    def Wait(entryIds: List[str], timeoutSec: float = 0) -> bool:
        """
        Blocks until all given Entries are COMPLETED or FAILED, and drives the scheduler
        itself, so it works with or without Job.Work(). timeoutSec 0 = wait forever.
        Returns False on timeout.
        """
        end: float = time.time() + timeoutSec
        while any(Job.Get(i).state not in Job.FINISHED for i in entryIds):
            if timeoutSec and time.time() > end:
                return False
            Job.Refresh()
            time.sleep(0.01)
        return True

    @staticmethod
    def Work(delayMs: int = 500) -> None:
        if Job.scheduler is None or not Job.scheduler.is_alive():
            Job.scheduler = JobScheduler(delayMs)
            Job.scheduler.start()

    @staticmethod
    def Stop() -> None:
        if Job.scheduler is not None:
            Job.scheduler.running = False
            Job.scheduler.join()
            Job.scheduler = None

# --- PRIVATE FUNCTIONS ---------------------------------------------------------------------------

    @staticmethod
    def _updateStates() -> None:
        # Parents come before their children, so one pass also propagates FAILED down the chain
        for e in Job.queue:
            if e.state is EntryState.RUNNING:
                e.command.status()
                if not e.command.running:
                    e.state = EntryState.COMPLETED if e.command.exitCode == 0 else EntryState.FAILED

            elif e.state is EntryState.WAITING_FOR_PARENT:
                parents: List[EntryState] = [Job.Get(p).state for p in e.parents]
                if e.always and e.waitFor:      # a closing step waits for its waitFor to end, however they ended
                    ended: bool = all(Job.Get(p).state in Job.FINISHED for p in e.waitFor)
                    parents = ([Job.Get(e.dependsOn).state] if e.dependsOn else []) + ([] if ended else [EntryState.RUNNING])
                if EntryState.FAILED in parents or EntryState.KILLED in parents:
                    e.state = EntryState.FAILED
                elif all(p is EntryState.COMPLETED for p in parents):
                    e.state = EntryState.READY4EXEC

        # One failure aborts the whole runlist: nothing new is started, except the closing steps
        aborted: set = {e.runlist for e in Job.queue if e.runlist and e.state is EntryState.FAILED}
        for e in Job.queue:
            if e.runlist in aborted and not e.always and e.state in {EntryState.WAITING_FOR_PARENT, EntryState.READY4EXEC}:
                e.state = EntryState.FAILED

    @staticmethod
    def _checkUrgent(e: Entry) -> None:
        """Takes over the result of an urgent Entry, or kills it when its deadline is over. Never touches the queue."""
        if e.state is not EntryState.RUNNING:
            return
        e.command.status()
        if not e.command.running:
            e.state = EntryState.COMPLETED if e.command.exitCode == 0 else EntryState.FAILED
        elif time.monotonic() > e.deadline:
            e.command.kill()
            e.command.killed = True
            e.command.status_msg.append("Deadline of " + str(e.deadlineMs) + " ms exceeded, " +
                                        ("process killed" if not e.command.running else "process does not die, given up"))
            e.state = EntryState.KILLED

    @staticmethod
    def _trimUrgent() -> None:
        # The registry of system commands must not grow without end: the oldest finished ones go first
        if len(Job.urgent) <= Job.URGENT_KEEP:
            return
        for e in Job.urgent:
            Job._checkUrgent(e)
        finished: List[Entry] = [e for e in Job.urgent if e.state in Job.FINISHED]
        for old in finished[:max(0, len(Job.urgent) - Job.URGENT_KEEP)]:
            Job.urgent.remove(old)

    @staticmethod
    def _startEntries() -> None:
        running: List[Entry] = [e for e in Job.queue if e.state is EntryState.RUNNING]
        cpuSlots: int = Job.limit - sum(1 for e in running if not e.tape)

        # A drive works strictly in queue order: only its oldest unfinished Entry may start
        nextOnDrive: dict = {}
        for e in Job.queue:
            if e.tape and e.state not in Job.FINISHED:
                nextOnDrive.setdefault(e.tape, e)

        ready: List[Entry] = [e for e in Job.queue if e.state is EntryState.READY4EXEC]
        for e in sorted(ready, key=Job._priority):  # sorted() is stable -> FIFO per priority
            if e.tape:
                if nextOnDrive[e.tape] is not e:
                    continue
            else:
                if cpuSlots <= 0:
                    continue
                cpuSlots -= 1

            if e.prepare is not None:
                try:
                    e.prepare()
                except Exception as ex:     # whatever the Command needed could not be made: it must not run
                    e.error = type(ex).__name__ + ": " + str(ex)
                    e.state = EntryState.FAILED
                    continue

            e.command.start()
            e.state = EntryState.RUNNING

    @staticmethod
    def _priority(e: Entry) -> int:
        if e.tape:
            return 0    # tape work
        if Job._leadsToTape(e):
            return 1    # prepares tape work
        return 2        # everything else

    @staticmethod
    def _leadsToTape(e: Entry) -> bool:
        for child in Job.queue:
            if e.id in child.parents and (child.tape or Job._leadsToTape(child)):
                return True
        return False

    @staticmethod
    def _updateJobState() -> None:
        if len(Job.queue) == 0:
            Job.state = JobState.EMPTY
        elif any(e.state is EntryState.RUNNING for e in Job.queue):
            Job.state = JobState.WORKING
        else:
            Job.state = JobState.IDLE

class JobScheduler(threading.Thread):

    def __init__(self, delayMs: int) -> None:
        super().__init__(daemon=True)
        self.running: bool = True
        self.delay: int = delayMs

    # This method calls Job.Refresh() every n ms
    def run(self) -> None:
        while self.running:
            Job.Refresh()
            time.sleep(self.delay / 1000)
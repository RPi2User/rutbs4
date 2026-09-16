from enum import Enum
import json
import os
import threading
import time
import uuid
from typing import List, Optional

from backend.Command import Command

class EntryState(Enum):
    FAILED = -1
    WAITING_FOR_PARENT = 0
    READY4EXEC = 1
    RUNNING = 2
    COMPLETED = 3

class Entry():

    """
    #### === ENTRY ============================================================

    Entry.__init__(command: Command, tape: str = "", dependsOn: str = ""):
    - Requires
        - A Command that has not been started yet
    - Supports
        - tape:      tape device (e.g. "/dev/nst0") if this Command uses a drive
        - dependsOn: id of the parent Entry, which must be COMPLETED first

    | Var              | Type         | Description                                     |
    |------------------|--------------|-------------------------------------------------|
    | `self.id`        | `str`        | UUID, returned by `Job.Add()`                   |
    | `self.command`   | `Command`    | The work itself                                 |
    | `self.tape`      | `str`        | Tape device, `""` for CPU/Disk work             |
    | `self.dependsOn` | `str`        | Parent id, `""` if there is no parent           |
    | `self.state`     | `EntryState` | See `Job` for the state flow                    |
    """

    def __init__(self, command: Command, tape: str = "", dependsOn: str = "") -> None:
        self.id: str = str(uuid.uuid4())
        self.command: Command = command
        self.tape: str = tape
        self.dependsOn: str = dependsOn
        self.state: EntryState = EntryState.WAITING_FOR_PARENT if dependsOn else EntryState.READY4EXEC

    def _asdict(self) -> dict:
        _out: dict = {
            "id": self.id,
            "state": self.state.name,
            "tape": self.tape,
            "dependsOn": self.dependsOn,
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

    Job schedules Commands. Each Entry may depend on ONE parent Entry.
    Parents must be added before their children, so the queue is always in
    dependency order and a single pass over it resolves the whole tree.

    Example (write a file to tape):
        c = Job.Add(Command("sha256sum a"))
        e = Job.Add(Command("encrypt a"),         dependsOn=c)
        w = Job.Add(Command("dd ... of=/dev/nst0"), tape="/dev/nst0", dependsOn=e)
        ...
        Job.Work()

    State flow of an Entry:
        WAITING_FOR_PARENT --parent COMPLETED--> READY4EXEC --> RUNNING --> COMPLETED
                           --parent FAILED-----> FAILED                 --> FAILED (exitCode != 0)

    Scheduling (every tick, in this order):
        1. Tape Entries          -> the tape must never idle, one Entry per drive
        2. Entries feeding tape  -> e.g. checksum/encryption before a tape write
        3. Everything else       -> e.g. decrypt/verify after the tape
        Same priority: first come, first serve. CPU work is limited by `Job.limit`.

    | `Job.`             | Description                                              |
    |--------------------|----------------------------------------------------------|
    | `Job.Add()`        | Adds a Command, returns the Entry id                     |
    | `Job.Get()`        | Returns the Entry of an id, raises LookupError           |
    | `Job.Registry()`   | Returns all Entries as dict                              |
    | `Job.Flush()`      | Kills & removes all, or (killRunning=False) removes done |
    | `Job.Refresh()`    | One scheduler tick: update states, start Entries         |
    | `Job.Work()`       | Starts the JobScheduler thread (calls Refresh)           |
    | `Job.Stop()`       | Stops the JobScheduler thread                            |
    """

    DEFAULT_THREADLIMIT: int = os.cpu_count() or 1
    FINISHED = {EntryState.COMPLETED, EntryState.FAILED}

    state: JobState = JobState.EMPTY
    queue: List[Entry] = []
    limit: int = DEFAULT_THREADLIMIT            # max. parallel CPU/Disk Entries
    lock: threading.RLock = threading.RLock()   # Add() and the scheduler thread share the queue
    scheduler: Optional["JobScheduler"] = None

# --- PUBLIC FUNCTIONS ----------------------------------------------------------------------------

    @staticmethod
    def Add(cmd: Command, tape: str = "", dependsOn: str = "") -> str:
        with Job.lock:
            if any(e.command is cmd for e in Job.queue):
                raise ValueError("ERROR: Command already queued, create a new Command object")
            if dependsOn != "":
                Job.Get(dependsOn)      # raises LookupError if the parent is unknown

            _e: Entry = Entry(cmd, tape, dependsOn)
            Job.queue.append(_e)
            Job._updateStates()         # parent might already be COMPLETED
            Job._updateJobState()
            return _e.id

    @staticmethod
    def Get(entryId: str) -> Entry:
        with Job.lock:
            for entry in Job.queue:
                if entry.id == entryId:
                    return entry
        raise LookupError("Entry not found: " + entryId)

    @staticmethod
    def Registry() -> dict:
        with Job.lock:
            return {entry.id: entry._asdict() for entry in Job.queue}

    @staticmethod
    def Flush(killRunning: bool = True) -> None:
        with Job.lock:
            if killRunning:
                for entry in Job.queue:
                    if entry.state is EntryState.RUNNING:
                        entry.command.kill()
                Job.queue.clear()
            else:
                Job._updateStates()     # a WAITING child never loses its unfinished parent
                Job.queue[:] = [e for e in Job.queue if e.state not in Job.FINISHED]
            Job._updateJobState()

    @staticmethod
    def Refresh() -> None:
        with Job.lock:
            Job._updateStates()
            Job._startEntries()
            Job._updateJobState()

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
                parent: EntryState = Job.Get(e.dependsOn).state
                if parent is EntryState.COMPLETED:
                    e.state = EntryState.READY4EXEC
                elif parent is EntryState.FAILED:
                    e.state = EntryState.FAILED

    @staticmethod
    def _startEntries() -> None:
        running: List[Entry] = [e for e in Job.queue if e.state is EntryState.RUNNING]
        busyDrives: set = {e.tape for e in running if e.tape}
        cpuSlots: int = Job.limit - sum(1 for e in running if not e.tape)

        ready: List[Entry] = [e for e in Job.queue if e.state is EntryState.READY4EXEC]
        for e in sorted(ready, key=Job._priority):  # sorted() is stable -> FIFO per priority
            if e.tape:
                if e.tape in busyDrives:
                    continue
                busyDrives.add(e.tape)
            else:
                if cpuSlots <= 0:
                    continue
                cpuSlots -= 1

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
            if child.dependsOn == e.id and (child.tape or Job._leadsToTape(child)):
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
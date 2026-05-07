from enum import Enum
import json
import threading
import os
import time
from typing import List
import uuid

from backend.Command import Command

class EntryState(Enum):
    INIT = -1
    RUNNING = 0
    COMPLETED = 1
    QUEUED = 2
    READY4EXEC = 3
    WAITING_FOR_PARENT = 4

class Entry():

    def __init__(self, command: Command, needsDependency: bool = False, fulfills: str = ""):
        self.command: Command = command
        self.id: str = str(uuid.uuid4())
        self.state: EntryState = EntryState.INIT
        self.needsDependency: bool = needsDependency
        self.dependsOn: str = ""
        self.fulfills: str = fulfills

    def _asdict(self) -> dict:
        _out : dict = {
            "id": self.id,
            "state": str(self.state.name),
            "dependsOn" : self.dependsOn,
            "fulfills" : self.fulfills,
            "command": self.command._asdict(),
        }
        return {"Entry": _out}

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

class JobState(Enum):
    ERROR = -3
    FLUSH = -2
    EMPTY = -1
    IDLE = 0
    WORKING = 1

class Job():

    """
    This class does all Scheduling in a List type.
    Each List Entry / Job Entry can have a dependency Tree.
    This Scheduler prioritizes Entry without Dependencies more than Entry with Dependencies.
    This Scheduler prioritizes Entries that fulfills dependency for completed Entries.
    When all Entries are atomic, this scheduler works after "first come, first serve"
    """

    DEFAULT_THREADLIMIT: int = os.cpu_count() or 1
    state: JobState = JobState.EMPTY

    queue: List[Entry] = []
    limit: int = DEFAULT_THREADLIMIT

    @staticmethod
    def Add(_cmd: Command, needsDependency: bool = False, fulfills: str = "") -> str:
        """
        This adds an Entry `e` to Job.queue.
        If `fulfills=q` is specified e gets noted in q.dependsOn=e.  
        """

        if Job.state is JobState.FLUSH:     # flush gets set when Job.flush(killRunning=False) gets called 
            Job.Flush(killRunning=False)    # remove old & completed jobs
            if Job.state is JobState.FLUSH:
                return                      # prevent appending when queue still needs to be flushed

        if len(Job.queue) == 0:
            Job.state = JobState.EMPTY      # this will clear any error States

        _e: Entry = Entry(_cmd, needsDependency, fulfills)

        if not needsDependency:
            _e.state = EntryState.READY4EXEC
            if fulfills != "":
                Job._checkDepTree(fulfills)


        # --- END ----------------
        Job.queue.append(_e)

        # This exception is purely optional, might fuck up the code at some point
        if Job.queue[-1].id != _e.id:
            Job.state = JobState.ERROR
            raise RuntimeError("[ERROR] JOB: - DATA CORRUPTION - Queue malformed, flush required!")

        Job.state = JobState.IDLE

        return Job.queue[-1].id

    @staticmethod # private
    def _checkDepTree(fulfillant: str) -> None:
        if Job.state in {JobState.ERROR, JobState.FLUSH}:
            return

        pass

    @staticmethod
    def Get(uuid: str) -> Entry:
        for entry in Job.queue:
            if entry.id == uuid:
                return entry
        raise LookupError("Entry not found!")

    @staticmethod
    def Flush(killRunning: bool = True) -> None:
        Job.state = JobState.FLUSH

        if killRunning:
            for entry in Job.queue:
                entry.command.kill()
            Job.queue.clear()
            Job.state = JobState.EMPTY 
            return

        for e in Job.queue:
            if e.state is not EntryState.RUNNING:
                Job.queue.remove(e)

    @staticmethod
    def Registry() -> dict:
        data = {}
        for entry in Job.queue:
            data.update({entry.id: entry._asdict()})
        return data

    @staticmethod
    def Work() -> None:
        scheduler = JobScheduler(500)
        scheduler.start()

    @staticmethod
    def Refresh() ->  None:
        """
        This starts cmd if we have capacity available:
        Easy example:
            1. Job._limit = 4
            2. Job.queue = []
            3. We add five commands sequentially (e.g.: first cmd runs 10sec, all others 60sec.)

        Job.queue:
            [QUEUED], [QUEUED], [QUEUED], [QUEUED], [QUEUED]
        Job.Work()
            [RUNNING], [RUNNING], [RUNNING], [RUNNING], [QUEUED]
        after 10sec & after a JobScheduler tick:
            [FINISHED], [RUNNING], [RUNNING], [RUNNING], [RUNNING]

        So our fifth Command gets started until 

        1. Get Inventory of all running processes (_running)
        2. If the current cmd is NOT running,  
        """

        for entry in Job.queue:
            _running: int = 0
            str(entry.command)    # Poll current status of current cmd
            if entry.command.running:
                _running += 1
            else:
                if _running > Job.limit:
                    entry.command.start()

class JobScheduler(threading.Thread):

    def __init__(self, delayMs: int):
        super().__init__(daemon=True)
        self.running: bool = True
        self.delay = delayMs

    # This method calls Job.refresh() every n ticks
    def run(self):
        while self.running:
            time.sleep(float(self.delay / 1000))
            Job.Refresh()

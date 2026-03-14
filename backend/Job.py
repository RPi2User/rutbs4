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

class Job():

    DEFAULT_THREADLIMIT: int = os.cpu_count() or 1

    queue: List[Entry] = []
    limit: int = DEFAULT_THREADLIMIT

    @staticmethod
    def Add(_cmd: Command, needsDependency: bool = False, fulfills: str = "") -> str:
        _e: Entry = Entry(_cmd, needsDependency, fulfills)

        if not needsDependency:
            _e.state = EntryState.READY4EXEC
            if fulfills != "":
                Job._checkDepTree(fulfills)


        # --- END ----------------
        Job.queue.append(_e)

        # This exception is purely optional, might fuck up the code at some point
        if Job.queue[-1].id != _e.id:
            raise RuntimeError("[ERROR] JOB: - DATA CORRUPTION - Queue malformed, flush required!")

        return Job.queue[-1].id

    @staticmethod # private
    def _checkDepTree(fulfillant: str) -> None:
        # this clears INIT state for dependency tree
        pass

    @staticmethod
    def Get(uuid: str) -> Entry:
        for entry in Job.queue:
            if entry.id == uuid:
                return entry
        return {}

    @staticmethod
    def Flush(killRunning: bool = True) -> None:
        pass

    @staticmethod
    def Registry() -> dict:
        FIXME
        data = {}
        for entry in Job.queue:
            data.update(entry._asdict())
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

from enum import Enum
import threading
import os
import time
from typing import List
import uuid

from backend.Command import Command

class EntryState(Enum):
    RUNNING = 0
    COMPLETED = 1
    QUEUED = 2
    WAITING_FOR_PARENT = 3

class Entry():

    def __init__(self, command: Command):
        self.command: Command = command
        self.id: str = str(uuid.uuid4())
        self.state: EntryState = EntryState.QUEUED
        self.dependsOn: str = ""

    def _asdict(self) -> dict:
        return {self.id: self.command._asdict()}

class Job():

    DEFAULT_THREADLIMIT: int = os.cpu_count() or 1

    queue: List[Entry] = []
    limit: int = DEFAULT_THREADLIMIT

    

    @staticmethod
    def Add(_cmd: Command) -> str:
        Job.queue.append(Entry(_cmd))
        return Job.queue[-1].id

    @staticmethod
    def Get(uuid: str) -> dict:
        for entry in Job.queue:
            if entry.id == uuid:
                return entry._asdict()
        return {}

    @staticmethod
    def Flush(killRunning: bool = True) -> None:
        pass

    @staticmethod
    def Registry() -> dict:
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

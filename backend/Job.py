import threading
import os
import time
from typing import List

from backend.Command import Command

class Job():

    DEFAULT_THREADLIMIT: int = os.cpu_count()

    queue: List[Command] = []
    _limit: int = DEFAULT_THREADLIMIT

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
            3. We add five commands sequentially (first cmd runs 10sec, all others 60sec.)

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

        for cmd in Job.queue:
            _running: int = 0
            str(cmd)    # Poll current status of current cmd
            if cmd.running:
                Job._running += 1
            else:
                if _running > Job._limit:
                    cmd.start()



    @staticmethod
    def Add(_cmd: Command) -> int:
        Job.queue.append(_cmd)
        return len(Job.queue) - 1

    @staticmethod
    def Get(id: int) -> dict:
        return Job.queue[id]._asdict()

    @staticmethod
    def Registry():
        return Job.queue._asdict()

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

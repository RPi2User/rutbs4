import json

from typing import List
from enum import Enum

from tbk.Status import Status
from backend.Command import Command
from backend.TapeDrive import TapeDrive
from backend.File import File
from backend.Folder import Folder
from backend.Checksum import Checksum, ChecksumType

class WS_States(Enum):
    WAIT_FOR_DRIVE = 0
    WAIT_FOR_CHECKSUM = 1
    CKSUM_ERROR = 2
    WRITE_ERROR = 3
    ERROR = 4

class WriteScheduler():

    # --- Vars -----------------------------------------------------
    state: WS_States = WS_States.ERROR
    drive: TapeDrive
    threadLimit: int
    cksum_type: ChecksumType
    folders: List[Folder] = []
    writePipeline: List[File] = []
    cksumPipeline: List[File] = []

    write_job: File
    cksum_jobs: List[File]
    failedCmd: Command
    # --------------------------------------------------------------


    def _initPipelines(self) -> None:
        for folder in self.folders:
            for file in folder.files:
                if self.cksum_type != ChecksumType.NONE:
                    self.cksumPipeline.append(file)
                else:
                    self.writePipeline.append(file)

    def _checkWriteJob(self):
        _driveState = self.drive.getStatus()
        if _driveState in {Status.TAPE_RDY, Status.NOT_AT_BOT}:
            self.write_job = None

    def _checkCksumJobs(self) -> None:
        # This empties completed Jobs
        if not self.cksum_jobs:
            return
        for job in self.cksum_jobs:
            # Check Status, so it'll commit the value
            job.checksum._status()

            # When job completed...
            if not job.checksum.cmd.running:
                # ... Check if error occured
                if job.checksum.cmd.exitCode != 0:
                    self.state = WS_States.CKSUM_ERROR
                    self.failedCmd = job.cmd
                    break
                else:
                    # ... Move this job to write-pipeline
                    self.writePipeline.append(job)
                    self.cksum_jobs.remove(job)


    def _assignJobs(self) -> None:
        if not self.write_job:
            if not self.writePipeline:
                self._checkCksumJobs()
            else:
                self.write_job = self.writePipeline.pop(0)
        else:
            self._checkWriteJob()

    def work(self):
        self.state = WS_States.WAIT_FOR_DRIVE


    # --- System ---------------------------------------------------
    # TODO: this shall get all information from the TOC!
    def __init__(self, tapeDrive: TapeDrive, targetFolders: List[Folder], threadLimit: int, cksum_type: ChecksumType = ChecksumType.SHA256) -> None:
        self.drive = tapeDrive
        self.folders = targetFolders
        if (threadLimit < 1):
            self.threadLimit = 1
        else:
            self.threadLimit = threadLimit
        self.cksum_type = cksum_type
        self._initPipelines()

    def _asdict(self) -> dict:
        jobs = {
            "write_job": self.writeJob,
            "cksum_jobs": [file._asdict() for file in self.cksum_jobs]
        }

        data =  {
            "issue": self.state.name,
            "drive": self.drive._asdict(),
            "running_jobs": jobs,
            "writePipeline": [file._asdict() for file in self.writePipeline],
            "cksumPipeline": [file._asdict() for file in self.cksumPipeline],
            "folders": [folder._asdict() for folder in self.folders],
        }
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict())
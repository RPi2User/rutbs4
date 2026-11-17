import json
import os
from enum import Enum
from typing import List

from backend.Encryption import E_Mode
from backend.File import File
from backend.Command import Command
from backend.Checksum import ChecksumType
from backend.Spool import Spool
from backend.TapeDrive import TapeDrive

class Folder:

    """
    All files below one directory, sub directories included, sharing one checksum type and
    one encryption mode. The files are sorted by relative path; that order is the tape
    order, and `File.id` is the tape file number (tape file 0 is the TOC, so ids start at 1).
    """

    def __init__(self, path: str, checksumType: ChecksumType, encryptionMode: E_Mode = E_Mode.NONE):
        self.files: List[File] = []
        self.path: str = path
        self.checksumType: ChecksumType = checksumType
        self.encMode: E_Mode = encryptionMode

        find_files: Command = Command("find " + Command.quote(path) + " -type f")
        find_files.wait()   # wait until the find process is finished, shall be instant

        # find does not promise any order, the tape order must not depend on it
        ordered: List[str] = sorted(find_files.stdout, key=lambda p: os.path.relpath(p, path))

        for _id, filepath in enumerate(ordered, start=1):
            file: File = File(_id, filepath, self.path)     # every File brings its own Key and IV
            file.cksum.setType(self.checksumType)
            file.encryption_scheme.mode = self.encMode
            self.files.append(file)

    def queueWrite(self, tapeDrive: TapeDrive, runlist: str = "", spool: Spool | None = None) -> List[str]:
        """
        Queues the phases Validate -> Encrypt -> Write of every File in this Folder (see File).
        Nothing is started here, Job.Work()/Job.Refresh() drives the actual execution.

        All Entries get the given runlist id: if one File fails, the Files after it are
        not written anymore (see Job).

        With a spool (already created) the encrypted Files are put there, named after their
        tape file number. Without one they are put next to the originals.

        Returns the Job entry ids of the tape-write Entries, so the caller can wait
        for them to reach EntryState.COMPLETED/FAILED.
        """
        write_entries: List[str] = []

        for file in self.files:
            entry: str = file.Validate(runlist=runlist)
            entry = file.Encrypt(spool.file(file.id) if spool else "", runlist=runlist, dependsOn=entry)
            write_entries.append(file.Write(tapeDrive, runlist=runlist, dependsOn=entry))

        return write_entries

    # SYSTEM
    def __str__(self) -> str:
        return json.dumps(self._asdict())
    
    def _asdict(self) -> dict:
        data = {
            "path": self.path,
            "encryption_type": self.encMode.name,
            "files" : [file._asdict() for file in self.files]
        }
        return data
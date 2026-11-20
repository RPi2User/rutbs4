import json
import os
from typing import List

from backend.Encryption import E_Mode, Encryption, Key
from backend.File import File
from backend.Command import Command
from backend.Job import Job
from backend.Checksum import ChecksumType
from backend.Spool import Spool
from backend.TapeDrive import TapeDrive

class Folder:

    """
    All files below one directory, sub directories included, sharing one checksum type and
    one encryption mode. The files are sorted by relative path; that order is the tape
    order, and `File.id` is the tape file number (tape file 0 is the TOC, so ids start at 1).
    The checksum defaults to SHA256 (pass `ChecksumType.NONE` to switch it off).
    """

    SCAN_DEADLINE_MS: int = 60000   # a big tree on a slow disk; not a system command in the 2 s sense

    def __init__(self, path: str, checksumType: ChecksumType = ChecksumType.SHA256, encryptionMode: E_Mode = E_Mode.NONE):
        self.files: List[File] = []
        self.path: str = path
        self._checksumType: ChecksumType = checksumType
        self._encMode: E_Mode = encryptionMode

        find_files: Command = Command("find " + Command.quote(path) + " -type f")
        Job.Run(find_files, deadlineMs=self.SCAN_DEADLINE_MS)
        if find_files.killed:   # an incomplete list would write an incomplete tape
            raise SystemError("[ERROR] Scanning " + path + " failed: " + " ".join(find_files.status_msg))

        # find does not promise any order, the tape order must not depend on it
        ordered: List[str] = sorted(find_files.stdout, key=lambda p: os.path.relpath(p, path))

        for _id, filepath in enumerate(ordered, start=1):
            file: File = File(_id, filepath, self.path)     # every File brings its own Key and IV
            file.cksum.setType(self._checksumType)
            file.encryption_scheme.mode = self._encMode
            self.files.append(file)

    # Both are decided with the request and cannot be changed afterwards: assigning raises AttributeError.
    # To change them, create a new Folder. The one exception is removeEncryption(), see TableOfContent.
    @property
    def checksumType(self) -> ChecksumType:
        return self._checksumType

    @property
    def encMode(self) -> E_Mode:
        return self._encMode

    def removeEncryption(self) -> None:
        """Every File becomes a plain one: mode NONE and no key. Only before anything is queued."""
        self._encMode = E_Mode.NONE
        for file in self.files:
            file.encryption_scheme = Encryption(Key(empty=True), E_Mode.NONE)

    def queueChecksums(self, runlist: str = "", drive: str = "") -> List[str]:
        """Queues the checksum of every File and returns the entry ids (in the order of the Files)."""
        return [file.Validate(runlist=runlist, drive=drive) for file in self.files]

    def queueWrite(self, tapeDrive: TapeDrive, runlist: str = "", spool: Spool | None = None,
                   checksums: List[str] | None = None) -> List[str]:
        """
        Queues the phases Validate -> Encrypt -> Write of every File in this Folder (see File).
        With `checksums` (from `queueChecksums()`) the Validate phase is queued already: Encrypt
        then waits for the checksum of its File.
        Nothing is started here, Job.Work()/Job.Refresh() drives the actual execution.

        All Entries get the given runlist id: if one File fails, the Files after it are
        not written anymore (see Job).

        With a spool (already created) the encrypted Files are put there, named after their
        tape file number. Without one they are put next to the originals.

        Returns the Job entry ids of the tape-write Entries, so the caller can wait
        for them to reach EntryState.COMPLETED/FAILED.
        """
        write_entries: List[str] = []

        for n, file in enumerate(self.files):
            entry: str = checksums[n] if checksums else file.Validate(runlist=runlist, drive=tapeDrive.id)
            entry = file.Encrypt(spool.file(file.id) if spool else "", runlist=runlist, dependsOn=entry, drive=tapeDrive.id)
            write_entries.append(file.Write(tapeDrive, runlist=runlist, dependsOn=entry))

        return write_entries

    # SYSTEM
    def __str__(self) -> str:
        return json.dumps(self._asdict(),indent=2)
    
    def _asdict(self) -> dict:
        data = {
            "path": self.path,
            "encryption_type": self.encMode.name,
            "files" : [file._asdict() for file in self.files]
        }
        return data
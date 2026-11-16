import json
from enum import Enum
from typing import List

from backend.Encryption import E_Mode
from backend.File import File
from backend.Command import Command
from backend.Checksum import ChecksumType
from backend.Job import Job
from backend.TapeDrive import TapeDrive

class Folder:


    def __init__(self, path: str, checksumType: ChecksumType, encryptionMode: E_Mode = E_Mode.NONE):
        self.files: List[File] = []
        self.path: str = path
        self.checksumType: ChecksumType = checksumType
        self.encMode: E_Mode = encryptionMode

        find_files: Command = Command("find " + Command.quote(path) + " -maxdepth 1 -type f")
        find_files.wait()   # wait until the find process is finished, shall be instant

        for _id, filepath in enumerate(find_files.stdout):
            file: File = File(_id, filepath, self.path)     # every File brings its own Key and IV
            file.cksum.setType(self.checksumType)
            file.encryption_scheme.mode = self.encMode
            self.files.append(file)

    def queueWrite(self, tapeDrive: TapeDrive, runlist: str = "") -> List[str]:
        """
        Registers Checksum -> Encryption -> tape write for every File in this Folder with the
        Job scheduler (see Job.py's own docstring example for the same pattern). Nothing is
        started here, Job.Work()/Job.Refresh() drives the actual execution.

        All Entries get the given runlist id: if one File fails, the Files after it are
        not written anymore (see Job).

        Returns the Job entry ids of the terminal tape-write Entries, so the caller can wait
        for them to reach EntryState.COMPLETED/FAILED.
        """
        write_entries: List[str] = []
        tapeDrive.tape.begin_of_tape = False

        for file in self.files:
            parent: str = ""
            write_path: str = file.path.path

            if self.checksumType != ChecksumType.NONE:
                file.cksum.create()
                parent = Job.Add(file.cksum.cmd, runlist=runlist)

            if self.encMode != E_Mode.NONE:
                file.encryption_scheme.encrypt(file.path.path)
                write_path = file.encryption_scheme.targetPath   # tape must read the ciphertext
                parent = Job.Add(file.encryption_scheme.cmd, dependsOn=parent, runlist=runlist)

            # Built directly (not via TapeDrive.write()), matching Job.py's own docstring
            # pattern: TapeDrive.write() assumes one write at a time and isn't meant to have
            # several Files queued against it before the first one has actually run.
            write_cmd: Command = Command(
                "dd if=" + Command.quote(write_path) + " of=" + Command.quote(tapeDrive.path) + " " +
                "iflag=fullblock status=none bs=" + tapeDrive.blocksize,
                filesize=file.size)
            write_entries.append(Job.Add(write_cmd, tape=tapeDrive.path, dependsOn=parent, runlist=runlist))

        return write_entries

    def finalizeChecksums(self) -> None:
        """
        Job only drives the raw Command objects, it never touches Checksum/Encryption
        themselves. Call this once the Job entries from queueWrite() are FINISHED so
        every File.cksum.value reflects the completed checksum (needed for the TOC / report).
        """
        for file in self.files:
            file.cksum._status()

    def encrypt(self):
        pass

    def decrypt(self):
        pass

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
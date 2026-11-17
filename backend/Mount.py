import json
from typing import List

from backend.Command import Command

class Mount:

    """
    One mounted file system, as reported by `findmnt`.

    | `Mount.`          | Description                                             |
    |-------------------|---------------------------------------------------------|
    | `Mount.list()`    | All mounted file systems (like `df`)                    |
    | `Mount.of(path)`  | The mount that holds `path`                             |
    """

    FIELDS: str = "TARGET,SOURCE,FSTYPE,SIZE,USED,AVAIL"

    def __init__(self, filesystem: str, fstype: str, size: int, used: int, mountpoint: str, avail: int = 0):
        self.filesystem = filesystem
        self.fstype = fstype
        self.size = size
        self.used = used
        self.mountpoint = mountpoint
        self.avail = avail

    @staticmethod
    def _parse(cmd: str) -> List["Mount"]:
        command: Command = Command(cmd)
        command.wait()
        if command.exitCode != 0 or not command.stdout:
            return []

        mounts: List[Mount] = []
        for fs in json.loads("\n".join(command.stdout))["filesystems"]:
            mounts.append(Mount(fs.get("source") or "", fs["fstype"], fs["size"], fs["used"], fs["target"], fs["avail"]))
        return mounts

    @staticmethod
    def list() -> List["Mount"]:
        return Mount._parse("findmnt -D -J -b -o " + Mount.FIELDS)

    @staticmethod
    def of(path: str) -> "Mount | None":
        found: List[Mount] = Mount._parse("findmnt -T " + Command.quote(path) + " -J -b -o " + Mount.FIELDS)
        return found[0] if found else None

    def _asdict(self) -> dict:
        return self.__dict__.copy()

    def __str__(self) -> str:
        return json.dumps(self._asdict())

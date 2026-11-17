import os
import shutil
import time

from backend.Mount import Mount

class Spool:

    """
    The spool directory of one job: `<mount>/rutbs-spool/<epoch>_<fingerprint>/`.
    It holds the encrypted files until the drive has taken them, named after their tape
    file number (`0001.crypt`) because two files in different directories may share a name.

    | `Spool.`           | Description                                                  |
    |--------------------|--------------------------------------------------------------|
    | `Spool(mountpoint, fingerprint)` | `mountpoint` must be a mount point, not just a directory |
    | `create()`         | Makes the directory (mode 0700) and returns its path         |
    | `file(id)`         | Path of the encrypted file with this tape file number        |
    | `remove()`         | Deletes the directory with everything in it (and `rutbs-spool` if empty) |
    """

    DIR: str = "rutbs-spool"

    def __init__(self, mountpoint: str, fingerprint: str, epoch: int = 0):
        mount: Mount | None = Mount.of(mountpoint)
        if mount is None or os.path.realpath(mountpoint) != mount.mountpoint:
            raise ValueError("'" + mountpoint + "' is not a mount point")

        self.mount: Mount = mount
        self.path: str = os.path.join(mountpoint, self.DIR, str(epoch or int(time.time())) + "_" + fingerprint)

    def create(self) -> str:
        os.makedirs(self.path, mode=0o700)      # exists already -> FileExistsError, a spool is never shared
        return self.path

    def file(self, id: int) -> str:
        return os.path.join(self.path, f"{id:04d}.crypt")

    def remove(self) -> None:
        if os.path.basename(os.path.dirname(self.path)) != self.DIR:    # never delete anything else
            raise ValueError("Not a spool directory: " + self.path)
        shutil.rmtree(self.path, ignore_errors=True)
        try:
            os.rmdir(os.path.dirname(self.path))    # the rutbs-spool directory, if no other job uses it
        except OSError:
            pass

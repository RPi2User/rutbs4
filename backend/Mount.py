import subprocess
import json

class Mount:

    def __init__(self, filesystem: str, fstype: str, size: int, used: int, mountpoint: str):
        self.filesystem = filesystem
        self.fstype = fstype
        self.size = size
        self.used = used
        self.mountpoint = mountpoint

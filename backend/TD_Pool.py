import json
import os
import re
from typing import Dict, List

from backend.TapeDrive import TapeDrive

class TD_Pool:

    """
    Finds the tape drives of this host. A SAS drive with two cables shows up twice
    (`/dev/sg12` and `/dev/sg13`, `/dev/nst0` and `/dev/nst1`) but is ONE drive.

    Who is the same drive is decided by the kernel, not by the serial number: the kernel
    reads the device identification (SCSI INQUIRY VPD page 0x83) of every device and
    publishes the id of the logical unit in sysfs as `wwid` (e.g. `naa.50050763121a839e`).
    Devices with the same `wwid` are one drive, and `TapeDrive.paths` lists all of them.

    A drive is never hidden: whenever the kernel made a `/dev/nstX` for it, it is listed. If it
    cannot be proven that two paths are one drive, they are listed as two, with a warning in
    `messages`: when there is no `wwid`, or when devices with the same `wwid` disagree on vendor
    or model. Only a tape without any `nst` device is left out (there is nothing to write to).

    | `TD_Pool.`          | Description                                                       |
    |---------------------|-------------------------------------------------------------------|
    | `scan()`            | Reads sysfs only, returns one dict per drive (no SCSI command)    |
    | `gatherDrives()`    | `scan()`, then one `TapeDrive` per drive (asks the drive, INQUIRY) |
    | `drives`            | the `TapeDrive` objects of the last `gatherDrives()`              |
    | `messages`          | what was refused and why                                          |
    """

    def __init__(self, sysfs: str = TapeDrive.SYSFS, dev: str = "/dev", drive_override: bool = False):
        self.sysfs: str = sysfs
        self.dev: str = dev
        self.drive_override: bool = drive_override  # no SCSI commands at all, for tests
        self.drives: List[TapeDrive] = []
        self.messages: List[str] = []

    def _read(self, sg: str, attribute: str) -> str:
        return TapeDrive.sysfsRead(sg, attribute, self.sysfs)

    def scan(self) -> List[dict]:
        self.messages = []
        groups: Dict[str, dict] = {}

        for sg in sorted(os.listdir(self.sysfs), key=lambda n: (len(n), n)):     # sg2 before sg10
            if self._read(sg, "type") != "1":       # 1 = tape
                continue

            tapeDir: str = os.path.join(self.sysfs, sg, "device", "scsi_tape")
            nst: List[str] = []
            if os.path.isdir(tapeDir):
                nst = [n for n in os.listdir(tapeDir) if re.fullmatch(r"nst\d+", n)]
            if not nst:     # nothing to write to, so there is no drive to offer
                self.messages.append("[ERROR] /dev/" + sg + " is a tape but has no non-rewinding tape device (st driver?)")
                continue

            path = (os.path.join(self.dev, nst[0]), os.path.join(self.dev, sg))
            wwid: str = self._read(sg, "wwid")
            vendor: str = self._read(sg, "vendor")
            model: str = self._read(sg, "model")

            # A drive the kernel made an nst device for is never hidden. If we cannot be sure that two
            # paths are one drive they are listed as two.
            if not wwid:
                self.messages.append("[WARNING] " + path[1] + ": the kernel publishes no wwid, listed as a drive of its own")
                groups["path:" + path[0]] = {"wwid": "", "vendor": vendor, "model": model, "paths": [path]}
                continue

            group = groups.get(wwid)
            if group is not None and (vendor, model) != (group["vendor"], group["model"]):
                self.messages.append("[WARNING] wwid " + wwid + ": " + path[1] + " is " + vendor + " " + model +
                                     " but another path is " + group["vendor"] + " " + group["model"] +
                                     ", listed as a drive of its own")
                groups[wwid + "#" + sg] = {"wwid": wwid, "vendor": vendor, "model": model, "paths": [path]}
                continue

            if group is None:
                group = groups.setdefault(wwid, {"wwid": wwid, "vendor": vendor, "model": model, "paths": []})
            group["paths"].append(path)

        return list(groups.values())

    def gatherDrives(self) -> List[TapeDrive]:
        self.drives = []
        for info in self.scan():
            first = info["paths"][0]
            drive: TapeDrive = TapeDrive(path=first[0], generic_path=first[1], drive_override=self.drive_override,
                                         paths=info["paths"], wwid=info["wwid"])
            drive.vendor = drive.vendor or info["vendor"]       # in case the drive was not asked
            drive.model = drive.model or info["model"]
            self.drives.append(drive)

        if not self.drives and not self.messages:
            self.messages.append("[INFO] No Drives Found")
        return self.drives

    def _asdict(self) -> dict:
        return {"drives": [d._asdict() for d in self.drives], "messages": self.messages}

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

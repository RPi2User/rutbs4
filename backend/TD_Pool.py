import json
import os
import re
from typing import Dict, List

from backend.TapeDrive import TapeDrive

class TD_Pool:

    """
    Finds the tape drives of this host. A SAS drive with two cables shows up twice
    (`/dev/nst0` and `/dev/nst1`, `/dev/sg12` and `/dev/sg13`) but is ONE drive.

    Who is the same drive is decided by the kernel, not by the serial number: the kernel
    reads the device identification (SCSI INQUIRY VPD page 0x83) of every device and
    publishes the id of the logical unit in sysfs as `wwid` (e.g. `naa.50050763121a839e`).
    Devices with the same `wwid` are one drive, and `TapeDrive.paths` lists all of them.

    The list starts from the `nst` devices, nothing else is needed. A drive is never hidden: whenever the
    kernel made a `/dev/nstX` for it, it is listed. Everything else the kernel tells (the `sg` device, `wwid`,
    vendor, model) is optional. If it cannot be proven that two paths are one drive, they are listed as two, with a
    warning in `messages`: when there is no `wwid`, or when devices with the same `wwid` disagree on vendor
    or model. Only a tape without any `nst` device is left out (there is nothing to write to).

    | `TD_Pool.`          | Description                                                       |
    |---------------------|-------------------------------------------------------------------|
    | `scan()`            | Reads sysfs only, returns one dict per drive (no SCSI command)    |
    | `gatherDrives()`    | `scan()`, then one `TapeDrive` per drive (asks the drive, INQUIRY) |
    | `drives`            | the `TapeDrive` objects of the last `gatherDrives()`              |
    | `messages`          | what was refused and why                                          |
    """

    SYSFS: str = "/sys/class"       # with scsi_tape and, optional, scsi_generic below

    def __init__(self, sysfs: str = SYSFS, dev: str = "/dev", drive_override: bool = False):
        self.sysfs: str = sysfs
        self.dev: str = dev
        self.drive_override: bool = drive_override  # no SCSI commands at all, for tests
        self.drives: List[TapeDrive] = []
        self.messages: List[str] = []

    @staticmethod
    def _natural(name: str) -> tuple:
        return (len(name), name)        # nst2 before nst10

    def _read(self, device: str, attribute: str) -> str:
        """What the kernel says about a device, `device` is e.g. "scsi_tape/nst0", "" if it says nothing."""
        try:
            with open(os.path.join(self.sysfs, device, "device", attribute)) as f:
                return f.read().strip()
        except OSError:
            return ""

    def _list(self, directory: str) -> List[str]:
        try:
            return sorted(os.listdir(os.path.join(self.sysfs, directory)), key=self._natural)
        except OSError:
            return []

    def _nstDevices(self) -> List[str]:
        names: List[str] = [n for n in self._list("scsi_tape") if re.fullmatch(r"nst\d+", n)]
        if not names:       # no sysfs: what /dev holds
            try:
                names = sorted((n for n in os.listdir(self.dev) if re.fullmatch(r"nst\d+", n)), key=self._natural)
            except OSError:
                pass
        return names

    def scan(self) -> List[dict]:
        self.messages = []
        groups: Dict[str, dict] = {}
        sgOfTapes: set = set()

        for nst in self._nstDevices():
            device: str = "scsi_tape/" + nst
            sg: List[str] = [n for n in self._list(device + "/device/scsi_generic") if re.fullmatch(r"sg\d+", n)]
            sgOfTapes.update(sg)

            path = (os.path.join(self.dev, nst), os.path.join(self.dev, sg[0]) if sg else "")
            name: str = path[0] + (" (" + path[1] + ")" if path[1] else "")
            wwid: str = self._read(device, "wwid")
            vendor: str = self._read(device, "vendor")
            model: str = self._read(device, "model")

            # A drive the kernel made an nst device for is never hidden. If we cannot be sure that two
            # paths are one drive they are listed as two.
            if not wwid:
                self.messages.append("[WARNING] " + name + ": the kernel publishes no wwid, listed as a drive of its own")
                groups["path:" + path[0]] = {"wwid": "", "vendor": vendor, "model": model, "paths": [path]}
                continue

            group = groups.get(wwid)
            if group is not None and (vendor, model) != (group["vendor"], group["model"]):
                self.messages.append("[WARNING] wwid " + wwid + ": " + name + " is " + vendor + " " + model +
                                     " but another path is " + group["vendor"] + " " + group["model"] +
                                     ", listed as a drive of its own")
                groups[wwid + "#" + nst] = {"wwid": wwid, "vendor": vendor, "model": model, "paths": [path]}
                continue

            if group is None:
                group = groups.setdefault(wwid, {"wwid": wwid, "vendor": vendor, "model": model, "paths": []})
            group["paths"].append(path)

        for sg in self._list("scsi_generic"):       # 1 = tape; nothing to write to, so there is no drive to offer
            if sg not in sgOfTapes and self._read("scsi_generic/" + sg, "type") == "1":
                self.messages.append("[ERROR] /dev/" + sg + " is a tape but has no non-rewinding tape device (st driver?)")

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

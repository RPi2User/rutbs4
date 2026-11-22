import os
import tempfile
import unittest
from typing import List

# Module imports
from backend.TapeDrive import TapeDrive
from backend.TD_Pool import TD_Pool


class UT_TD_Pool(unittest.TestCase):

    """_summary_
    Builds a fake sysfs (`scsi_tape`, `scsi_generic`) like the one of a host with a dual-cabled LTO drive.
    Tests A:
        - A: two sg devices with the same wwid are ONE drive with two paths, natural sg order
        - B: nothing is hidden: no wwid, same wwid but different model are listed on their own; only a tape
             without nst device is left out; disks are ignored
        - C: gatherDrives() builds the TapeDrive objects, the drive id is the same on every path
        - D: TapeDrive reads its own wwid from sysfs
        - E: without sg devices (no sg driver) and without sysfs the nst devices are still listed
    Depdencies:
    - none (no SCSI command is sent)
    """

    def _device(self, root: str, sg: str, type: str = "1", nst: str = "", wwid: str = "",
                vendor: str = "IBM     ", model: str = "ULT3580-HH8     ") -> None:
        device: str = os.path.join(root, "devices", sg or nst)      # sysfs: both classes link to the same device
        os.makedirs(device)
        attributes: dict = {"type": type, "vendor": vendor, "model": model, "wwid": wwid}
        for name, value in attributes.items():
            if value:
                with open(os.path.join(device, name), "w") as f:
                    f.write(value + "\n")
        for cls, names in (("scsi_generic", [sg] if sg else []),
                           ("scsi_tape", [nst, nst + "a", nst + "l", nst + "m", nst[1:], nst[1:] + "a"] if nst else [])):   # nst0, nst0a, .., st0, st0a
            for name in names:
                os.makedirs(os.path.join(root, cls, name))
                os.symlink(device, os.path.join(root, cls, name, "device"))
                os.makedirs(os.path.join(device, cls, name))

    def _host(self, tmp: str) -> str:
        root: str = os.path.join(tmp, "class")
        self._device(root, "sg0", type="0", model="HGST HUS724040AL")                      # a disk
        self._device(root, "sg1", nst="nst0", wwid="naa.50050763121a839e")                 # drive A, cable 1
        self._device(root, "sg2", nst="nst1", wwid="naa.50050763121a839e")                 # drive A, cable 2
        self._device(root, "sg3", nst="nst2", wwid="naa.5005076300000002", model="ULT3580-HH6")   # drive B
        self._device(root, "sg10", nst="nst3", wwid="naa.5005076300000002", model="ULT3580-HH6")  # drive B, sg10 after sg3
        self._device(root, "sg4", nst="nst4")                                              # no wwid
        self._device(root, "sg5", wwid="naa.5005076300000003")                             # tape without nst device
        self._device(root, "sg6", nst="nst5", wwid="naa.5005076300000004")                 # same wwid ...
        self._device(root, "sg7", nst="nst6", wwid="naa.5005076300000004", model="ULT3580-HH5")  # ... other model
        return root

    def test_A_samewwidIsOneDrive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            drives: dict = {d["wwid"]: d for d in TD_Pool(self._host(tmp), "/dev").scan()}

            a: dict = drives["naa.50050763121a839e"]
            self.assertEqual(a["paths"], [("/dev/nst0", "/dev/sg1"), ("/dev/nst1", "/dev/sg2")])
            self.assertEqual((a["vendor"], a["model"]), ("IBM", "ULT3580-HH8"))

            b: dict = drives["naa.5005076300000002"]
            self.assertEqual(b["paths"], [("/dev/nst2", "/dev/sg3"), ("/dev/nst3", "/dev/sg10")])  # nst2 before nst3
        print(".A_SAME_WWID")

    def test_B_nothingIsHidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool: TD_Pool = TD_Pool(self._host(tmp), "/dev")
            drives: List[dict] = pool.scan()

            # every nst device is in exactly one drive, none is lost
            listed: List[str] = sorted(p[0] for d in drives for p in d["paths"])
            self.assertEqual(listed, sorted("/dev/nst" + str(n) for n in [0, 1, 2, 3, 4, 5, 6]))

            self.assertEqual(len(drives), 5)    # A (2 paths), B (2 paths), sg4, sg6, sg7
            lone: List[dict] = [d for d in drives if len(d["paths"]) == 1]
            self.assertEqual(sorted(d["paths"][0][1] for d in lone), ["/dev/sg4", "/dev/sg6", "/dev/sg7"])
            self.assertEqual([d["wwid"] for d in lone if d["paths"][0][1] == "/dev/sg4"], [""])   # no wwid

            self.assertEqual(len(pool.messages), 3)
            self.assertTrue(any("sg4" in m and "nst4" in m and "no wwid" in m and m.startswith("[WARNING]") for m in pool.messages))
            self.assertTrue(any("naa.5005076300000004" in m and "ULT3580-HH5" in m and "of its own" in m for m in pool.messages))
            self.assertTrue(any("sg5" in m and "no non-rewinding" in m for m in pool.messages))     # the one without nst
        print("B_NOTHING_HIDDEN")

    def test_C_gatherDrives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool: TD_Pool = TD_Pool(self._host(tmp), "/dev", drive_override=True)
            drives = pool.gatherDrives()

            self.assertEqual(len(drives), 5)
            a: TapeDrive = drives[0]
            self.assertEqual((a.path, a.generic_path), ("/dev/nst0", "/dev/sg1"))     # first path is used
            self.assertEqual(len(a.paths), 2)
            self.assertEqual(a.id, "naa.50050763121a839e")
            self.assertEqual(a.vendor, "IBM")

            # the same drive reached over its second cable has the same id: Job runs one command at a time on it
            other: TapeDrive = TapeDrive("/dev/nst1", "/dev/sg2", drive_override=True, wwid=a.wwid)
            self.assertEqual(other.id, a.id)
            self.assertEqual(a._asdict()["environment"]["paths"][1], {"path": "/dev/nst1", "generic_path": "/dev/sg2"})
        print("C_GATHER")

    def test_D_driveReadsItsWwid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root: str = self._host(tmp)
            self.assertEqual(TapeDrive.sysfsRead("/dev/sg1", "wwid", os.path.join(root, "scsi_generic")), "naa.50050763121a839e")
            self.assertEqual(TapeDrive.sysfsRead("/dev/sg4", "wwid", os.path.join(root, "scsi_generic")), "")      # kernel says nothing
            self.assertEqual(TapeDrive.sysfsRead("", "wwid", os.path.join(root, "scsi_generic")), "")

            plain: TapeDrive = TapeDrive("/tmp/faketape", "", drive_override=True)   # no sg device: the path identifies it
            self.assertEqual(plain.id, "/tmp/faketape")
        print("D_OWN_WWID")

    def test_E_onlyNst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root: str = os.path.join(tmp, "class")
            self._device(root, "", nst="nst0", wwid="naa.1")                    # no sg driver
            self._device(root, "", nst="nst10")
            self._device(root, "", nst="nst2")
            pool: TD_Pool = TD_Pool(root, "/dev")
            self.assertEqual([d["paths"] for d in pool.scan()], [[("/dev/nst0", "")], [("/dev/nst2", "")], [("/dev/nst10", "")]])

            dev: str = os.path.join(tmp, "dev"); os.makedirs(dev)
            for name in ["nst0", "nst0a", "st0", "nst1", "sda"]:
                open(os.path.join(dev, name), "w").close()
            pool = TD_Pool(os.path.join(tmp, "missing"), dev)                   # no sysfs at all
            self.assertEqual([d["paths"][0][0] for d in pool.scan()], [os.path.join(dev, "nst0"), os.path.join(dev, "nst1")])
            self.assertEqual(TD_Pool(os.path.join(tmp, "missing"), os.path.join(tmp, "none")).scan(), [])
        print("E_ONLY_NST")


if __name__ == "__main__":
    unittest.main()

import os
import unittest

# Module imports
from backend.Mount import Mount
from backend.Spool import Spool


class UT_Spool(unittest.TestCase):

    """_summary_
    Tests A:
        - A:  Mount.of() and Mount.list() find /mnt/daten as a mount
        - B:  Spool is created on the mount, with the expected name and mode, and removed again
        - C:  Only mount points are accepted, a spool is never shared
    Depdencies:
    - /mnt/daten is a mount (absolute path, like the fixtures)
    - findmnt
    """

    MOUNT: str = "/mnt/daten"

    def setUp(self) -> None:
        if not os.path.ismount(self.MOUNT):
            self.skipTest(self.MOUNT + " is not a mount")

    def test_A_mountIsRecognised(self) -> None:
        mount: Mount = Mount.of(self.MOUNT)     # type: ignore
        self.assertEqual(mount.mountpoint, self.MOUNT)
        self.assertGreater(mount.size, 0)
        self.assertGreater(mount.avail, 0)

        # a path below the mount belongs to the same mount
        self.assertEqual(Mount.of(self.MOUNT + "/testfiles").mountpoint, self.MOUNT)    # type: ignore
        self.assertIsNone(Mount.of(self.MOUNT + "/does/not/exist"))
        self.assertIn(self.MOUNT, [m.mountpoint for m in Mount.list()])

    def test_B_createAndRemove(self) -> None:
        spool: Spool = Spool(self.MOUNT, "ut-spool", epoch=1234)
        self.assertEqual(spool.path, "/mnt/daten/rutbs-spool/1234_ut-spool")
        self.assertEqual(spool.file(7), "/mnt/daten/rutbs-spool/1234_ut-spool/0007.crypt")

        try:
            spool.create()
            self.assertTrue(os.path.isdir(spool.path))
            self.assertEqual(os.stat(spool.path).st_mode & 0o777, 0o700)

            with open(spool.file(1), "w") as f:
                f.write("x")
        finally:
            spool.remove()

        self.assertFalse(os.path.exists(spool.path))
        self.assertFalse(os.path.exists(os.path.join(self.MOUNT, Spool.DIR)))   # leaves nothing behind

    def test_C_rejects(self) -> None:
        with self.assertRaises(ValueError):
            Spool(self.MOUNT + "/testfiles", "ut-spool")   # a directory, not a mount point

        spool: Spool = Spool(self.MOUNT, "ut-spool-twice", epoch=1)
        try:
            spool.create()
            with self.assertRaises(FileExistsError):
                spool.create()
        finally:
            spool.remove()

        spool.path = "/mnt/daten/testfiles"
        with self.assertRaises(ValueError):
            spool.remove()      # refuses to delete anything that is not a spool


if __name__ == "__main__":
    unittest.main()

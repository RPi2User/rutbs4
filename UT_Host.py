import sys
import types
import unittest
from time import time

# Module imports
from backend.Command import Command
from backend.Job import Job

# Host still imports the old `tbk` package (gone from the repo, only used for type names there).
# Where it is missing a placeholder is enough for these tests; the real one is used if it exists.
try:
    import tbk.TDv2, tbk.TableOfContent     # noqa: E401
except ImportError:
    for _name, _attr in [("tbk", None), ("tbk.TDv2", "TapeDrive"), ("tbk.TableOfContent", "TableOfContent")]:
        _module = types.ModuleType(_name)
        if _attr:
            setattr(_module, _attr, object)
        sys.modules[_name] = _module
    sys.modules["tbk"].TDv2 = sys.modules["tbk.TDv2"]                       # type: ignore
    sys.modules["tbk"].TableOfContent = sys.modules["tbk.TableOfContent"]   # type: ignore

try:
    from backend.Host import Host
except ImportError as ex:       # flask, psutil or the old tbk package are not installed here
    Host = None
    IMPORT_ERROR: str = str(ex)


class FakeDrive:

    "Just what Host.drive_eject() looks at. NEVER a real drive: this test must not move a tape."

    def __init__(self, alias: str, bsy: bool = False, answer: str = "running") -> None:
        self.alias: str = alias
        self.bsy: bool = bsy
        self.status: str = "FAKE"
        self.path: str = "/dev/null"
        self.answer: str = answer
        self.issued: int = 0

    def eject(self):
        self.issued += 1
        if self.answer == "invalid":
            return None
        cmd: Command = Command("ping localhost -c 10")      # a command that is still running when drive_eject() answers
        Job.Add(cmd, urgent=True, deadlineMs=60000)
        return cmd


@unittest.skipIf(Host is None, "Host needs flask and psutil")
class UT_Host(unittest.TestCase):

    """_summary_
    Tests A:
        - A: eject of an unknown drive (404), of a busy one (503 and Retry-After)
        - B: eject does not wait for the command and tells exactly what happened (202)
        - C: a drive that cannot take an eject answers 409 and nothing was issued
    Depdencies:
    - flask, psutil (docs/requirements.txt); the old tbk package is replaced by a placeholder if missing
    - ping
    """

    def setUp(self) -> None:
        Job.Flush()
        self.host = Host.__new__(Host)      # no discovery, no real drives
        self.host.refresh_status = lambda: None
        self.drives = [FakeDrive("a"), FakeDrive("busy", bsy=True), FakeDrive("invalid", answer="invalid")]
        self.host.drives = self.drives

    def tearDown(self) -> None:
        Job.Flush()

    def test_A_unknown_and_busy(self) -> None:
        r = self.host.drive_eject("nope")
        self.assertEqual((r.status_code, r.get_data(as_text=True)), (404, "Drive not found."))
        r = self.host.drive_eject("busy")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.headers["Retry-After"], "120")
        self.assertEqual([d.issued for d in self.drives], [0, 0, 0])
        print("A_UNKNOWN_BUSY")

    def test_B_does_not_wait(self) -> None:
        beg: float = time()
        r = self.host.drive_eject("a")
        self.assertLess(time() - beg, 1)                    # the eject (a ping of 10 s) is still running
        self.assertEqual((r.status_code, r.get_data(as_text=True)), (202, "Issued Eject Command to TapeDrive."))
        self.assertEqual(self.drives[0].issued, 1)
        self.assertTrue(any(e.state.name == "RUNNING" for e in Job.urgent))
        print("B_DOES_NOT_WAIT")

    def test_C_invalid_state(self) -> None:
        r = self.host.drive_eject("invalid")
        self.assertEqual(r.status_code, 409)
        self.assertIn("Invalid State", r.get_data(as_text=True))
        self.assertEqual(self.drives[2].issued, 1)          # asked once, answered "cannot"
        self.assertEqual(Job.urgent, [])
        print("C_INVALID_STATE")


if __name__ == '__main__':
    print("UT_Host:")
    unittest.main()

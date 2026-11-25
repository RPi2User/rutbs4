import json
import sys
import uuid
from typing import Dict, List

from backend import TapeIoctl
from backend.Command import Command
from backend.Job import Job
from backend.Version import Version

class CartridgeMemory:

    """
    #### === CartridgeMemory ==================================================

    The chip in the cartridge (MAM), read and written with READ / WRITE ATTRIBUTE, see TapeIoctl. It is optional: a drive, tape
    or HBA without a usable chip leaves the fields empty and `error` filled (an `aic79xx` HBA refuses the command, it
    is 16 bytes long); the tape works without it.

    | Attribute | Format | Bytes | Content                                          |
    |-----------|--------|-------|--------------------------------------------------|
    | `0x0801`  | ASCII  | 32    | `appName`, always `rutbs`                        |
    | `0x0802`  | ASCII  | 8     | `version`, the backend version as 4 hex digits   |
    | `0x0803`  | text   | 160   | `fingerprint`, a UUID                            |

    Reading and writing are steps of the queue of the drive, like `Rewind()`. Nothing is read by itself.

    Example:
        cm = CartridgeMemory("/dev/nst0", td.id)
        Job.Wait([cm.read()])
        if cm.fingerprint == "":
            cm.format()         # ALWAYS a new fingerprint
            Job.Wait([cm.entry])
        print(cm)

    The fields change when a step is finished and succeeded, not before. A failed write keeps
    the old values and sets `error`.

    | `CartridgeMemory.`  | Description                                                          |
    |---------------------|----------------------------------------------------------------------|
    | `read()`            | Queues the reading of the chip, returns the entry id                 |
    | `format()`          | Queues the writing of name, version and a NEW fingerprint, see `entry` |
    | `cmd`, `entry`      | The last `Command` and its `Job` Entry id, `None` / `""` if none     |
    | `appName`, `version`, `fingerprint`, `error` | `""` if unknown                            |
    """

    ID_NAME: int = 0x0801
    ID_VERSION: int = 0x0802
    ID_LABEL: int = 0x0803
    APP_NAME: str = "tbkd"

    def __init__(self, device: str = "", drive: str = "", tool: str = "") -> None:
        self.device: str = device               # non-rewinding device of the drive, e.g. /dev/nst0
        self.drive: str = drive or device       # TapeDrive.id, the queue of the drive
        self.tool: str = tool or Command.quote(sys.executable) + " " + Command.quote(TapeIoctl.__file__)
        self.cmd: Command | None = None
        self.entry: str = ""
        self._appName: str = ""
        self._version: str = Version.text()
        self._fingerprint: str = ""
        self._error: str = ""
        self._pending: Dict[str, str] | None = None     # what a running write will make of the fields, {} for a read

# --- PUBLIC FUNCTIONS ----------------------------------------------------------------------------

    @property
    def appName(self) -> str:
        self._refresh()
        return self._appName

    @property
    def version(self) -> str:
        self._refresh()
        return self._version

    @property
    def fingerprint(self) -> str:
        self._refresh()
        return self._fingerprint

    @property
    def error(self) -> str:
        self._refresh()
        return self._error

    def _add(self, command: str, pending: Dict[str, str]) -> str:
        self._refresh()
        if self._pending is not None:
            raise RuntimeError("ERROR: A step on the cartridge memory is still running")
        if not self.device:
            raise ValueError("ERROR: No device for the cartridge memory")
        self.cmd = Command(self.tool + " " + command)
        self.entry = Job.Add(self.cmd, tape=self.drive)
        self._pending = pending
        return self.entry

    def read(self) -> str:
        """Queues the reading, returns the entry id. The fields follow when it succeeded."""
        return self._add("readattr " + Command.quote(self.device), {})

    def format(self) -> str:
        """Always makes a new fingerprint. Queues the writing, returns the entry id; the fields follow when it succeeded."""
        pending: Dict[str, str] = {"appName": self.APP_NAME, "version": Version.text(), "fingerprint": str(uuid.uuid4())}
        return self._add("writeattr " + Command.quote(self.device) + " " + pending["appName"] + " " + "%04x" % Version.word() +
                         " " + pending["fingerprint"], pending)

    @staticmethod
    def parse(lines: List[str]) -> Dict[int, str]:  # TODO when TD_Ioctl is static, use it properly
        """
        The hex dump of `TapeIoctl.py readattr`: an offset, then the bytes of the answer. The answer is
        4 bytes with the length of the rest, then per attribute id (2), format (1), length (2), value.
        Format 0 binary, 1 ASCII, 2 text; only the last two are returned, as text without padding.
        """
        data: bytearray = bytearray()
        for line in lines:
            for token in line.split()[1:]:
                data.append(int(token, 16))
        if len(data) < 4:
            raise ValueError("no answer")
        end: int = 4 + int.from_bytes(data[:4], "big")
        if end > len(data):
            raise ValueError("answer is cut off")

        out: Dict[int, str] = {}
        pos: int = 4
        while pos < end:
            if pos + 5 > end or pos + 5 + int.from_bytes(data[pos + 3:pos + 5], "big") > end:
                raise ValueError("attribute is cut off")
            attrId: int = int.from_bytes(data[pos:pos + 2], "big")
            fmt: int = data[pos + 2] & 0x3
            size: int = int.from_bytes(data[pos + 3:pos + 5], "big")
            if fmt in (1, 2):
                out[attrId] = bytes(data[pos + 5:pos + 5 + size]).decode("utf-8", errors="replace").rstrip(" \0")
            pos += 5 + size
        return out

# --- PRIVATE FUNCTIONS ---------------------------------------------------------------------------

    def _refresh(self) -> None:
        """Takes over a finished step; a running one changes nothing yet."""
        if self._pending is None or self.cmd is None:
            return
        try:
            if Job.Get(self.entry).state not in Job.FINISHED:
                return
        except LookupError:
            pass        # dropped from the registry, the Command itself knows the result
        self.cmd.status()
        if self.cmd.running:
            return
        pending: Dict[str, str] = self._pending
        self._pending = None
        if not self.cmd.didRun or self.cmd.exitCode != 0:
            self._error = ("WRITE" if pending else "READ") + " ATTRIBUTE failed: " + " ".join(self.cmd.status_msg + self.cmd.stderr)
            if not pending:
                self._appName = self._version = self._fingerprint = ""
        elif pending:
            self._appName, self._version, self._fingerprint = pending["appName"], pending["version"], pending["fingerprint"]
            self._error = ""
        else:
            self._takeOver()

    def _takeOver(self) -> None:
        self._appName = self._version = self._fingerprint = ""
        try:
            attributes: Dict[int, str] = self.parse(self.cmd.stdout)      # type: ignore
        except ValueError as ex:
            self._error = "READ ATTRIBUTE answer not readable: " + str(ex)
            return

        self._error = ""
        self._appName = attributes.get(self.ID_NAME, "")
        self._fingerprint = attributes.get(self.ID_LABEL, "")
        word: str = attributes.get(self.ID_VERSION, "")
        try:
            self._version = Version.fromWord(int(word, 16)) if word else ""
        except ValueError:
            self._version = word            # not written by us, show it as it is

    def _asdict(self) -> dict:
        return {
            "appName": self.appName,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "error": self.error,
        }

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

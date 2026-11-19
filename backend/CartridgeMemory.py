import json
import uuid
from typing import Dict, List

from backend.Command import Command
from backend.Job import EntryState, Job
from backend.Version import Version

class CartridgeMemory:

    """
    #### === CartridgeMemory ==================================================

    The chip in the cartridge (MAM), read and written with `sg_read_attr` / `sg_write_attr`.
    Reading is attempted, a drive or tape without a usable chip leaves the fields empty and
    `error` filled; the tape works without it.

    | Attribute | Format | Bytes | Content                                          |
    |-----------|--------|-------|--------------------------------------------------|
    | `0x0801`  | ASCII  | 32    | `appName`, always `rutbs`                        |
    | `0x0802`  | ASCII  | 8     | `version`, the backend version as 4 hex digits   |
    | `0x0803`  | text   | 160   | `fingerprint`, a UUID                            |

    Example:
        cm = CartridgeMemory("/dev/sg12")
        if cm.fingerprint == "":
            cm.format()         # ALWAYS a new fingerprint, starts sg_write_attr
            Job.Wait([cm.entry])    # the chip is slow, the write has `WRITE_DEADLINE_MS`
        print(cm)

    The fields change when the write is finished and succeeded, not before. A failed write keeps
    the old values and sets `error`.

    | `CartridgeMemory.`  | Description                                                          |
    |---------------------|----------------------------------------------------------------------|
    | `read()`            | Reads the chip, an urgent `Job` Entry with `READ_DEADLINE_MS`        |
    | `format()`          | Starts writing name, version and a NEW fingerprint, see `entry`      |
    | `cmd`, `entry`      | The last `Command` and its `Job` Entry id, `None` / `""` if none     |
    | `appName`, `version`, `fingerprint`, `error` | `""` if unknown                            |
    """

    ID_NAME: int = 0x0801
    ID_VERSION: int = 0x0802
    ID_LABEL: int = 0x0803
    APP_NAME: str = "rutbs"
    READ_DEADLINE_MS: int = 2000        # a query takes a few ms on a healthy drive
    WRITE_DEADLINE_MS: int = 60000      # the chip is slow

    def __init__(self, device: str = "", readTool: str = "sg_read_attr", writeTool: str = "sg_write_attr") -> None:
        self.device: str = device               # generic device of the drive, e.g. /dev/sg12
        self.readTool: str = readTool
        self.writeTool: str = writeTool
        self.cmd: Command | None = None
        self.entry: str = ""
        self._appName: str = ""
        self._version: str = ""
        self._fingerprint: str = ""
        self._error: str = ""
        self._pending: Dict[str, str] | None = None     # what a running write will make of the fields

        if device:
            self.read()

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

    def read(self) -> None:
        self._refresh()
        if self._pending is not None:
            raise RuntimeError("ERROR: A write to the cartridge memory is still running")
        if not self.device:
            raise ValueError("ERROR: No device to read the cartridge memory from")

        self._appName = self._version = self._fingerprint = ""
        self.cmd = Job.Run(Command(self.readTool + " -R -H " + Command.quote(self.device)), self.READ_DEADLINE_MS)
        if self.cmd.exitCode != 0:
            self._error = "READ ATTRIBUTE failed: " + " ".join(self.cmd.status_msg + self.cmd.stderr)
            return
        try:
            attributes: Dict[int, str] = self.parse(self.cmd.stdout)
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

    def format(self) -> None:
        """Always makes a new fingerprint. Returns at once, wait for `cmd`; the fields follow when it succeeded."""
        self._refresh()
        if self._pending is not None:
            raise RuntimeError("ERROR: A write to the cartridge memory is still running")
        if not self.device:
            raise ValueError("ERROR: No device to write the cartridge memory to")

        pending: Dict[str, str] = {"appName": self.APP_NAME, "version": Version.text(), "fingerprint": str(uuid.uuid4())}
        self.cmd = Command(self.writeTool + " " + Command.quote(self.device) +
                           " AppName=" + pending["appName"] +
                           " AppVersion=" + "%04x" % Version.word() +
                           " UserLabel=" + pending["fingerprint"])
        self.entry = Job.Add(self.cmd, urgent=True, deadlineMs=self.WRITE_DEADLINE_MS)
        self._pending = pending

    @staticmethod
    def parse(lines: List[str]) -> Dict[int, str]:
        """
        The hex dump of `sg_read_attr -H`: an offset, then the bytes of the answer. The answer is
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
        """Takes over a finished write; a running one changes nothing yet."""
        if self._pending is None or self.cmd is None:
            return
        try:
            killed: bool = Job.Get(self.entry).state is EntryState.KILLED     # looking at it drives the deadline
        except LookupError:
            killed = False      # dropped from the registry, the Command itself knows the result
        self.cmd.status()
        if self.cmd.running and not killed:
            return
        if self.cmd.exitCode == 0 and not killed:
            self._appName = self._pending["appName"]
            self._version = self._pending["version"]
            self._fingerprint = self._pending["fingerprint"]
            self._error = ""
        else:
            self._error = "WRITE ATTRIBUTE failed: " + " ".join(self.cmd.status_msg + self.cmd.stderr)
        self._pending = None

    def _asdict(self) -> dict:
        return {
            "appName": self.appName,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "error": self.error,
        }

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

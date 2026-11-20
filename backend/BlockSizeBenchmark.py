import json
import re
import uuid
from typing import Dict, List, Tuple

from backend.Job import EntryState, Job
from backend.Tape import E_Tape
from backend.TapeDrive import TapeDrive

class BlockSizeBenchmark:

    """
    The block size benchmark of the tape format (see docs/TapeFormat.md). It is destructive on purpose:
    for each candidate the tape is rewound and test data is written from its begin, then the tape is
    rewound once more. It never ejects. Nothing is written to the cartridge memory here.

        >>> bench = BlockSizeBenchmark(td)
        >>> bench.queue()
        >>> bench.wait()
        >>> print(bench)

    | `BlockSizeBenchmark.` | Description                                                          |
    |-----------------------|----------------------------------------------------------------------|
    | `queue()`             | Checks the request, queues everything, returns the ids               |
    | `wait(timeout)`       | Blocks until everything is finished, False on timeout                |
    | `state`               | `NEW`, `RUNNING` or `COMPLETED`                                      |
    | `results`             | `{block size in bytes: bytes/s}`, only the candidates that were measured |
    | `blocksize`, `note`   | the pick as text (`"256K"`) and the hint that goes with it, `""` if none |
    | `pick(results, ideal)` | the rule, a pure function: block size in bytes and note           |

    The rule: every block size with at least 90 % of the ideal rate of the cartridge (`Tape.native_rate`)
    is good enough, of those the smallest is taken: a smaller block is kinder to the HBA and the driver
    buffer. If the LTO version has no known ideal rate, the best measured speed is the yardstick.
    If even the best block size stays below 90 %, the note warns how much of the bandwidth is usable (a
    half height drive or a worn tape?) and the smallest block size within 90 % of the best one is taken.
    Only if nothing could be measured, `DEFAULT` is taken and the note says so.

    A candidate that fails (the driver or the HBA refuses the block size) is left out and does not
    stop the others: every step is a closing step (`always`) and the steps do not depend on each other,
    the drive works its queue in order anyway. Each candidate writes the same amount of data,
    `native_rate` times `seconds` (or `size` bytes), so it runs long enough for the tape mechanics
    to reach full speed.
    """

    DEFAULT: int = 256 * 1024
    # No candidate below 128K: the speed differences below it are noise, and HP asks for 128 KiB at least per transfer.
    CANDIDATES: List[int] = [DEFAULT] + [n * 64 * 1024 for n in (2, 3, 5, 6, 7, 8, 12, 16, 32, 64)]
    TOLERANCE: float = 0.1                  # a block size may be 10 % below the ideal rate
    SECONDS: int = 30
    UNKNOWN_RATE: int = 100 * 10**6         # bytes/s, to size the test if the LTO version has no ideal rate
    NOTHING: str = "Nothing could be measured, 256K is used."
    WARNING: str = "Warning: only {percent} % of the ideal bandwidth is usable. Is this a half height drive or a worn tape?"
    STATS = re.compile(r"(\d+) bytes .*copied, ([\d.]+) s")

    @staticmethod
    def label(blocksize: int) -> str:
        "262144 -> `256K`, 1048576 -> `1M`"
        return f"{blocksize >> 20}M" if blocksize % (1 << 20) == 0 else f"{blocksize >> 10}K"

    @staticmethod
    def pick(results: Dict[int, float], ideal: float = 0) -> Tuple[int, str]:
        "The rule, see the class doc. `results` is {block size: bytes/s}, `ideal` bytes/s or 0 if unknown."
        if not results:
            return BlockSizeBenchmark.DEFAULT, BlockSizeBenchmark.NOTHING
        best: float = max(results.values())
        warning: str = ""
        if ideal and best < (1 - BlockSizeBenchmark.TOLERANCE) * ideal:
            warning = BlockSizeBenchmark.WARNING.format(percent=round(100 * best / ideal))
            ideal = 0                           # the best one is the yardstick now
        limit: float = (1 - BlockSizeBenchmark.TOLERANCE) * (ideal or best)
        return min(bs for bs, rate in results.items() if rate >= limit), warning

    def __init__(self, tapeDrive: TapeDrive, seconds: int = SECONDS, size: int = 0, candidates: List[int] | None = None):
        self.drive: TapeDrive = tapeDrive
        self.size: int = size or int((tapeDrive.tape.native_rate or self.UNKNOWN_RATE) * seconds)
        self.candidates: List[int] = list(candidates or self.CANDIDATES)
        self.runlist: str = str(uuid.uuid4())
        self.entries: List[str] = []
        self.steps: List[Tuple[int, str]] = []      # (block size, entry id of its write)

    def queue(self) -> List[str]:
        if self.entries:
            raise RuntimeError("This benchmark is queued already")
        tape = self.drive.tape
        if tape.state is E_Tape.NO_TAPE:
            raise ValueError("No tape in the drive")
        if tape.write_protect:
            raise ValueError("The tape is write protected")

        r: str = self.runlist
        for bs in self.candidates:
            self.drive.Rewind(runlist=r, always=True)
            self.steps.append((bs, self.drive.WriteRandom(self.size, bs, runlist=r, always=True)))
        self.drive.Rewind(runlist=r, always=True)

        with Job.lock:
            self.entries = [e.id for e in Job.queue if e.runlist == r]
        return self.entries

    def wait(self, timeoutSec: float = 0) -> bool:
        return Job.Wait(self.entries, timeoutSec)

    @property
    def state(self) -> str:
        if not self.entries:
            return "NEW"
        return "RUNNING" if any(Job.Get(e).state not in Job.FINISHED for e in self.entries) else "COMPLETED"

    @property
    def results(self) -> Dict[int, float]:
        out: Dict[int, float] = {}
        for bs, entryId in self.steps:
            entry = Job.Get(entryId)
            if entry.state is not EntryState.COMPLETED:
                continue
            for line in entry.command.stderr:       # dd prints its stats after it closed the tape: the flush is in the time
                found = self.STATS.search(line)
                if found and float(found.group(2)) > 0:
                    out[bs] = int(found.group(1)) / float(found.group(2))
        return out

    @property
    def blocksize(self) -> str:
        return self.label(self.pick(self.results, self.drive.tape.native_rate)[0])

    @property
    def note(self) -> str:
        return self.pick(self.results, self.drive.tape.native_rate)[1]

    def _asdict(self) -> dict:
        ideal: int = self.drive.tape.native_rate
        results: Dict[int, float] = self.results
        table: List[dict] = []
        for bs, entryId in self.steps:
            row: dict = {"blocksize": self.label(bs), "state": Job.Get(entryId).state.name}
            if bs in results:
                row["MiB_s"] = round(results[bs] / 2**20, 1)
                if ideal:
                    row["percent_of_ideal"] = round(100 * results[bs] / ideal)
            table.append(row)
        return {
            "runlist": self.runlist,
            "state": self.state,
            "drive": self.drive.id,
            "ideal_MiB_s": round(ideal / 2**20, 1),
            "bytes_per_candidate": self.size,
            "results": table,
            "blocksize": self.blocksize,
            "note": self.note,
        }

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

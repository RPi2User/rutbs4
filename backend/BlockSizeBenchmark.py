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
    | `rate(stderr)`        | bytes/s of one write, the middle of the run, a pure function |
    | `blocksize`, `note`   | the pick as text (`"256K"`) and the hint that goes with it, `""` if none |
    | `pick(results, ideal)` | the rule, a pure function: block size in bytes and note           |

    The rule: 64K (`FALLBACK`) only counts if nothing bigger could be written. Of the others, every block size with at least 90 % of the ideal rate of the cartridge (`Tape.native_rate`)
    is good enough, of those the smallest is taken: a smaller block is kinder to the HBA and the driver
    buffer. If the LTO version has no known ideal rate, the best measured speed is the yardstick.
    If even the best block size stays below 90 %, the note warns how much of the bandwidth is usable (a
    half height drive or a worn tape?) and the smallest block size within 90 % of the best one is taken.
    Only if nothing could be measured, `DEFAULT` is taken and the note says so.

    A candidate that fails (the driver or the HBA refuses the block size) is left out and does not
    stop the others: every step is a closing step (`always`) and a write only depends on the rewind before it,
    the drive works its queue in order anyway. Each candidate writes the same amount of data,
    `native_rate` times `seconds` (or `size` bytes). Few sizes are measured for a long time, and the speed is that
    of the middle of the run (see `rate()`): spin up and spin down of the tape distort a short run.
    """

    DEFAULT: int = 128 * 1024
    # 128K is the reference and the default: HP asks for 128 KiB at least per transfer. 64K is only the fallback for a drive that takes
    # nothing bigger. 4M is the limit of some HBAs (aic79xx), bigger sizes are for SAS drives from LTO-8 on.
    CANDIDATES: List[int] = [n * 1024 for n in (128, 64, 256, 384, 512, 1024, 4096)]
    FALLBACK: int = 64 * 1024               # measured, but only picked if nothing bigger works
    TOLERANCE: float = 0.1                  # a block size may be 10 % below the ideal rate
    SECONDS: int = 120
    HEAD: int = 20                          # seconds left out: the tape has to spin up and the drive buffer fills
    TAIL: int = 5                           # seconds left out at the end: the flush, the file mark and the spin down
    MIN_SAMPLES: int = 10                   # fewer progress reports in the middle: the whole run is taken
    UNKNOWN_RATE: int = 100 * 10**6         # bytes/s, to size the test if the LTO version has no ideal rate
    NOTHING: str = "Nothing could be measured, 128K is used."
    ONLY_FALLBACK: str = "Warning: only 64K works, no bigger block size."
    WARNING: str = "Warning: only {percent} % of the ideal bandwidth is usable. Is this a half height drive or a worn tape?"
    STATS = re.compile(r"(\d+) bytes [^\r]*?copied, ([\d.]+) s")

    @staticmethod
    def rate(stderr: List[str]) -> float:
        """
        Bytes/s of a write out of what `dd status=progress` said, 0 if it said nothing usable. The spin up and the spin down
        of the tape distort the whole run, so only the middle counts: the slope of the progress reports (one per
        second) without the first `HEAD` and the last `TAIL` seconds. A run too short for that counts as a whole.
        """
        points: List[Tuple[float, int]] = [(float(m.group(2)), int(m.group(1)))
                                           for line in stderr for m in BlockSizeBenchmark.STATS.finditer(line)]
        points = [p for p in points if p[0] > 0]
        if not points:
            return 0
        seconds, size = points[-1]                  # the last line is the result of the whole run
        middle: List[Tuple[float, int]] = [p for p in points[:-1]
                                           if BlockSizeBenchmark.HEAD <= p[0] <= seconds - BlockSizeBenchmark.TAIL]
        if len(middle) < BlockSizeBenchmark.MIN_SAMPLES:
            return size / seconds
        t: float = sum(p[0] for p in middle) / len(middle)
        b: float = sum(p[1] for p in middle) / len(middle)
        spread: float = sum((p[0] - t) ** 2 for p in middle)
        return sum((p[0] - t) * (p[1] - b) for p in middle) / spread if spread else size / seconds

    @staticmethod
    def label(blocksize: int) -> str:
        "262144 -> `256K`, 1048576 -> `1M`"
        return f"{blocksize >> 20}M" if blocksize % (1 << 20) == 0 else f"{blocksize >> 10}K"

    @staticmethod
    def pick(results: Dict[int, float], ideal: float = 0) -> Tuple[int, str]:
        "The rule, see the class doc. `results` is {block size: bytes/s}, `ideal` bytes/s or 0 if unknown."
        if not results:
            return BlockSizeBenchmark.DEFAULT, BlockSizeBenchmark.NOTHING
        bigger: Dict[int, float] = {bs: rate for bs, rate in results.items() if bs > BlockSizeBenchmark.FALLBACK}
        if not bigger:
            return min(results), BlockSizeBenchmark.ONLY_FALLBACK
        results = bigger
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
            rewound: str = self.drive.Rewind(runlist=r, always=True)     # without a tape dd would wait for one
            self.steps.append((bs, self.drive.WriteRandom(self.size, bs, runlist=r, dependsOn=rewound, always=True)))
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
            measured: float = self.rate(entry.command.stderr)
            if measured:
                out[bs] = measured
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

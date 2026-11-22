#!/usr/bin/env python3
"""
Block size benchmark of one tape (see docs/TapeFormat.md): for each candidate block size the tape is rewound
and incompressible test data is written from its begin, 120 s worth of the ideal rate by default; the spin up and
spin down of the tape are left out of the measurement. The tape is
OVERWRITTEN on purpose and NOT ejected. Prints the table and the block size to use; nothing is stored on the tape.

Example (real LTO drive, the first drive found):
    python3 benchmark_tape.py

Example (no hardware, a regular file as tape; small amount of data):
    python3 benchmark_tape.py --tape /tmp/faketape.bin --size 20000000 --rewind-cmd true
"""

import argparse
import sys

from backend.BlockSizeBenchmark import BlockSizeBenchmark
from backend.Command import Command
from backend.Job import Job
from backend.Tape import Tape
from backend.TapeDrive import TapeDrive
from backend.TD_Pool import TD_Pool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=int, default=BlockSizeBenchmark.SECONDS, help="Duration of one candidate at the ideal rate")
    parser.add_argument("--size", type=int, default=0, help="Bytes per candidate instead of --seconds")
    parser.add_argument("--blocksizes", default="", help="Comma separated candidates in KiB, e.g. 256,384,512 (default: all)")
    parser.add_argument("--tape", default="", help="A regular file instead of the first drive found, for local testing")
    parser.add_argument("--rewind-cmd", default="", help="Rewind command of the fake tape")
    parser.add_argument("--lto-version", default="3", help="LTO version of the fake tape")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.tape:
        td = TapeDrive(args.tape, "", drive_override=True)
        td.tapeOverride(Tape(args.lto_version + "800", td.generic_path))
        td.rewindCommand = Command(args.rewind_cmd or "true")
    else:
        pool = TD_Pool()
        drives = pool.gatherDrives()
        for message in pool.messages:
            print(message, file=sys.stderr)
        if not drives:
            print("[ERROR] No tape drive found", file=sys.stderr)
            return 1
        td = drives[0]

    candidates = [int(n) * 1024 for n in args.blocksizes.split(",")] if args.blocksizes else None
    try:
        bench = BlockSizeBenchmark(td, args.seconds, args.size, candidates)
        bench.queue()
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    print(f"Writing {bench.size} bytes per block size to {td.id}, {len(bench.candidates)} candidates, the tape is overwritten")
    bench.wait()
    print(bench)
    if bench.note:
        print(f"[WARNING] {bench.note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Restore a tape to a folder: one ReadJob (read the first TOC, ask for the passphrase, then every file is read,
decrypted and checked against its checksum; the last TOC decides whether the tape is valid). The passphrase comes from RUTBS_PASSPHRASE or is asked for.
The tape is rewound and NOT ejected.

Example (real LTO drive, the first drive found):
    python3 read_tape_to_folder.py --target /path/to/restore --spool /stornvme --toc-dir /path/to/tocs
"""

import argparse
import getpass
import os
import sys

from backend.Job import Job
from backend.ReadJob import ReadJob
from backend.TD_Pool import TD_Pool
from backend.TableOfContent import TOC_WrongPassphrase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="Folder to restore into (must not hold the files yet)")
    parser.add_argument("--spool", required=True, help="Mount point for the spool (needs as much free space as the files)")
    parser.add_argument("--toc-dir", default="", help="Directory that keeps both TOCs in clear text after a good restore")
    parser.add_argument("--threads", type=int, default=4, help="Thread limit of the Job queue")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    Job.KillAtExit()
    Job.limit = args.threads

    pool = TD_Pool()
    drives = pool.gatherDrives()
    for message in pool.messages:
        print(message, file=sys.stderr)
    if not drives:
        print("[ERROR] No tape drive found", file=sys.stderr)
        return 1
    td = drives[0]

    try:
        job = ReadJob(td, args.target, args.spool, tocDir=args.toc_dir)
        print(f"Looking at the tape in {td.id} ...")
        header = job.open()
    except (ValueError, RuntimeError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    print(f"Tape {header['fingerprint']} written {header['created']} on {header['hostname']}")

    given = os.environ.get("RUTBS_PASSPHRASE")
    plain = header["body_cipher"] == "NONE"      # nothing to ask for
    for attempt in range(1 if given or plain else 3):
        passphrase = "" if plain else given or getpass.getpass("Passphrase for this tape: ")
        try:
            job.queue(passphrase)
            break
        except TOC_WrongPassphrase as e:
            print(f"[ERROR] {e}", file=sys.stderr)
        except ValueError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1
    else:
        return 1

    for message in job.messages:
        print(message, file=sys.stderr)
    print(f"Restoring {len(job.files)} files to {args.target}")
    job.wait()
    print(job)
    return 0 if job.state == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())

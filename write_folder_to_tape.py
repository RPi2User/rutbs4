#!/usr/bin/env python3
"""
Write a folder to tape: one WriteJob (every file checksummed, rewind, first TOC, every file encrypted with
its own key and written, last TOC, rewind). The passphrase comes from RUTBS_PASSPHRASE or is
asked for; with --encryption none there is no passphrase and the TOC is plain. The tape is NOT ejected unless --eject is given.

Example (real LTO drive, the first drive found):
    RUTBS_PASSPHRASE=... python3 write_folder_to_tape.py --dir /path/to/folder --spool /stornvme

Example (no SCSI tooling / no hardware, a regular file as tape):
    RUTBS_PASSPHRASE=... python3 write_folder_to_tape.py --dir /path/to/folder --spool /mnt/data \\
        --tape /tmp/faketape.bin --rewind-cmd true --eject-cmd true
"""

import argparse
import getpass
import os
import sys

from backend.Checksum import ChecksumType
from backend.Command import Command
from backend.Encryption import E_Mode
from backend.Job import Job
from backend.Tape import Tape
from backend.TapeDrive import TapeDrive
from backend.TD_Pool import TD_Pool
from backend.WriteJob import WriteJob

CHECKSUM_MAP = {
    "md5": ChecksumType.MD5,
    "sha256": ChecksumType.SHA256,
    "sha512": ChecksumType.SHA512,
    "none": ChecksumType.NONE,
}

ENCRYPTION_MAP = {
    "none": E_Mode.NONE,
    "aes128cbc": E_Mode.AES128CBC,
    "aes256cbc": E_Mode.AES256CBC,
    "aes128ctr": E_Mode.AES128CTR,
    "aes256ctr": E_Mode.AES256CTR,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Folder to write, sub directories included")
    parser.add_argument("--spool", required=True, help="Mount point for the spool (needs as much free space as the folder)")
    parser.add_argument("--toc-dir", default="", help="Directory that keeps a copy of the last TOC")
    parser.add_argument("--checksum", choices=sorted(CHECKSUM_MAP), default="sha256")
    parser.add_argument("--encryption", choices=sorted(ENCRYPTION_MAP), default="aes256cbc")
    parser.add_argument("--threads", type=int, default=4, help="Thread limit of the Job queue")
    parser.add_argument("--eject", action="store_true", help="Eject the tape after a successful write (off by default)")
    parser.add_argument("--tape", default="", help="A regular file instead of the first drive found, for local testing")
    parser.add_argument("--rewind-cmd", default="", help="Rewind command of the fake tape")
    parser.add_argument("--eject-cmd", default="", help="Eject command of the fake tape")
    parser.add_argument("--lto-version", default="8", help="LTO version of the fake tape")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    unencrypted = args.encryption == "none"
    passphrase = "" if unencrypted else os.environ.get("RUTBS_PASSPHRASE") or getpass.getpass("Passphrase for this tape: ")
    Job.limit = args.threads

    if args.tape:
        td = TapeDrive(args.tape, "", drive_override=True)
        td.tapeOverride(Tape(args.lto_version + "800", td.generic_path))     # <ltoVersion>800 -> valid Tape, no write protect
        td.rewindCommand = Command(args.rewind_cmd or "true")
        td.ejectCommand = Command(args.eject_cmd or "true")
    else:
        pool = TD_Pool()
        drives = pool.gatherDrives()
        for message in pool.messages:
            print(message, file=sys.stderr)
        if not drives:
            print("[ERROR] No tape drive found", file=sys.stderr)
            return 1
        td = drives[0]

    try:
        job = WriteJob(args.dir, td, passphrase, args.spool, tocDir=args.toc_dir,
                       checksum=CHECKSUM_MAP[args.checksum], encryption=ENCRYPTION_MAP[args.encryption], eject=args.eject,
                       unencrypted=unencrypted)
        job.queue()
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    print(f"Writing {len(job.folder.files)} files from {args.dir} to {td.id}, tape fingerprint {job.toc.header.fingerprint}")
    job.wait()
    print(job)
    return 0 if job.state == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Write a folder to tape, file-by-file: each file is checksummed, optionally encrypted (every
file with its own key) and written to tape with an EOF mark, orchestrated through
Job (see backend/Job.py).

Example (real LTO drive):
    RUTBS_PASSPHRASE=... python3 write_folder_to_tape.py --dir /path/to/folder --tape /dev/nst0 --generic /dev/sg0

Example (no SCSI tooling / no hardware, test against a regular file):
    python3 write_folder_to_tape.py --dir /path/to/folder --tape /tmp/faketape.bin \\
        --drive-override --rewind-cmd "true"
"""

import argparse
import getpass
import os
import sys
import time
import uuid

from backend.Checksum import ChecksumType
from backend.Command import Command
from backend.Encryption import E_Mode
from backend.Folder import Folder
from backend.Job import Job
from backend.Tape import Tape
from backend.TableOfContent import TableOfContent, TOC_Header
from backend.TapeDrive import TapeDrive, TD_State

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
    parser.add_argument("--dir", required=True, help="Folder to write (files directly inside it, non-recursive)")
    parser.add_argument("--tape", required=True, help="Non-rewinding tape device (/dev/nstX), or a regular file for local testing")
    parser.add_argument("--generic", default="", help="Generic SCSI device (/dev/sgX); leave empty together with --drive-override")
    parser.add_argument("--checksum", choices=sorted(CHECKSUM_MAP), default="sha256")
    parser.add_argument("--encryption", choices=sorted(ENCRYPTION_MAP), default="aes256cbc")
    parser.add_argument("--blocksize", default="256K", help="dd block size, e.g. 256K or 384K")
    parser.add_argument("--lto-version", default="3", help="LTO version, only used together with --drive-override")
    parser.add_argument("--drive-override", action="store_true",
                         help="Skip the sg_raw INQUIRY/MODE SENSE calls (needed when sg3_utils isn't installed, "
                              "or when --tape is a regular file instead of a real tape device)")
    parser.add_argument("--rewind-cmd", default="",
                         help="Command used to rewind the tape (only used together with --drive-override), "
                              "e.g. 'mt -f /dev/nst0 rewind'")
    return parser.parse_args()


def get_passphrase() -> str:
    """The passphrase of the tape: from RUTBS_PASSPHRASE, else asked for. Never a command line argument (visible in ps)."""
    return os.environ.get("RUTBS_PASSPHRASE") or getpass.getpass("Passphrase for this tape: ")


def wait_for(predicate, timeout: float = 30.0, interval: float = 0.1) -> bool:
    end = time.time() + timeout
    while not predicate():
        if time.time() > end:
            return False
        time.sleep(interval)
    return True


def main() -> int:
    args = parse_args()

    td = TapeDrive(path=args.tape, generic_path=args.generic, drive_override=args.drive_override, blocksize=args.blocksize)

    if args.drive_override:
        td.tapeOverride(Tape(args.lto_version + "800"))  # <ltoVersion>800 -> valid Tape, no write protect
        if args.rewind_cmd:
            td.rewindCommand = Command(args.rewind_cmd)

    folder = Folder(args.dir, CHECKSUM_MAP[args.checksum], ENCRYPTION_MAP[args.encryption])
    if not folder.files:
        print(f"[ERROR] No files found directly in {args.dir}", file=sys.stderr)
        return 1

    print(f"Folder: {args.dir} ({len(folder.files)} files), checksum={args.checksum}, encryption={args.encryption}")

    def rewind_finished() -> bool:
        td._refresh()
        return td.state != TD_State.REWIND

    print(f"Rewinding {args.tape} ...")
    td.rewind()
    if not wait_for(rewind_finished):
        print("[ERROR] Rewind timed out", file=sys.stderr)
        return 1
    if td.state == TD_State.ERROR:
        print("[ERROR] Rewind failed", file=sys.stderr)
        return 1

    passphrase = get_passphrase()
    if not passphrase:
        print("[ERROR] A passphrase is required, the TOC holds the keys", file=sys.stderr)
        return 1

    header = TOC_Header(td, threadCount=1)
    toc = TableOfContent(folder, header)
    td.writeTOC(toc.seal(passphrase))
    if td.state == TD_State.ERROR:
        print("[ERROR] Failed to write TOC", file=sys.stderr)
        return 1
    print("TOC written.")

    entries = folder.queueWrite(td, runlist=str(uuid.uuid4()))
    Job.Work(200)
    finished = wait_for(lambda: all(Job.Get(e).state in Job.FINISHED for e in entries), timeout=3600)
    Job.Stop()
    if not finished:
        print("[ERROR] Timed out waiting for the write pipeline", file=sys.stderr)
        return 1

    folder.finalizeChecksums()

    all_ok = True
    for file, entry_id in zip(folder.files, entries):
        entry = Job.Get(entry_id)
        ok = entry.state.name == "COMPLETED"
        all_ok = all_ok and ok
        print(f"  [{'OK' if ok else 'FAILED'}] {file.path.name}  ({args.checksum}={file.cksum.value})")
        if ENCRYPTION_MAP[args.encryption] != E_Mode.NONE:   # needed to decrypt again!
            print(f"         key: {file.encryption_scheme.key.value}  iv: {file.encryption_scheme.key.iv}")

    print("All files written successfully." if all_ok else "Some files FAILED, see above.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

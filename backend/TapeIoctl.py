"""
Rewind and eject of a tape through the kernel driver (`st`), without `mt` and without `sg_raw`:

    python3 TapeIoctl.py rewind /dev/nst0
    python3 TapeIoctl.py eject  /dev/nst0

Through the driver, because a rewind with `sg_raw` goes behind its back: once a read met the end of the data the
driver answers every later read with an I/O error, and only its own rewind clears that (measured on an LTO-3, 2026-11-22).

The device is opened with O_NONBLOCK: a normal open waits 2 minutes for a tape if there is none (`dd` does, too).
So a rewind answers at once and is the way to ask the drive whether it can take an order:

| Exit code       | Meaning                                                       |
|-----------------|---------------------------------------------------------------|
| 0               | done                                                          |
| `NO_MEDIUM` 10  | no tape in the drive (ENOMEDIUM)                              |
| `BUSY` 11       | somebody else has the device open, e.g. a running dd (EBUSY)  |
| 1               | everything else, the reason is on stderr                      |
"""

import errno
import fcntl
import os
import struct
import sys

MTIOCTOP: int = 0x40086D01      # _IOW('m', 1, struct mtop {short mt_op; int mt_count;})
OPERATIONS: dict = {"rewind": 6, "eject": 7}    # MTREW, MTOFFL (rewind and unload)
NO_MEDIUM: int = 10
BUSY: int = 11


def exitCode(number: int) -> int:
    return {errno.ENOMEDIUM: NO_MEDIUM, errno.EBUSY: BUSY}.get(number, 1)


def operate(operation: str, device: str) -> None:
    """Raises OSError if the driver refuses."""
    fd: int = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    try:
        fcntl.ioctl(fd, MTIOCTOP, struct.pack("hi", OPERATIONS[operation], 1))
    finally:
        os.close(fd)


def main(args: list) -> int:
    if len(args) != 2 or args[0] not in OPERATIONS:
        print("Usage: TapeIoctl.py " + "|".join(OPERATIONS) + " <device>", file=sys.stderr)
        return 2
    try:
        operate(args[0], args[1])
    except OSError as e:
        print(args[0] + " " + args[1] + ": " + errno.errorcode.get(e.errno or 0, "") + " " + str(e.strerror), file=sys.stderr)
        return exitCode(e.errno or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

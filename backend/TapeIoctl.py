"""
Everything that is asked of a tape drive except `dd`: ioctls on the non-rewinding device (`/dev/nstX`) of the kernel driver (`st`).
No `mt`, no sg3_utils, no `/dev/sgX`.

    python3 TapeIoctl.py rewind    /dev/nst0
    python3 TapeIoctl.py eject     /dev/nst0
    python3 TapeIoctl.py readattr  /dev/nst0                              the cartridge memory, as a hex dump
    python3 TapeIoctl.py writeattr /dev/nst0 <name> <version> <label>     the cartridge memory

The four are steps of the Job queue, like `dd`: the drive works on one thing at a time. `status()`, `serial()` are asked
in the process itself, they do not move the tape and never wait for long, see `TapeDrive`.

The device is opened with O_NONBLOCK: a normal open waits 2 minutes for a tape if there is none (`dd` does, too).
So a rewind answers at once and is the way to ask the drive whether it can take an order.

TOOD: mt-st does block until ejecting / rewinding is complete. Why does mt-st "know" that rewind/eject is complete?

A rewind also switches the drive to variable block mode (MTSETBLK 0): then every write of `dd` is one block on the tape
and the last block of a file may be shorter. In a fixed mode (`mt setblk 512`, `/etc/stinit.def`, another program) the
block size of `dd` has no effect on the tape, and a file that is no multiple of the block fails. A rewind alone does not
change the mode. If the drive refuses the switch the rewind fails, before anything is written.

| Exit code       | Meaning                                                       |
|-----------------|---------------------------------------------------------------|
| 0               | done                                                          |
| `NO_MEDIUM` 10  | no tape in the drive (ENOMEDIUM)                              |
| `BUSY` 11       | somebody else has the device open, e.g. a running dd (EBUSY)  |
| `NOT_READY` 12  | the drive loads or unloads a tape right now (EIO, and neither ready nor empty) |
| 1               | everything else, the reason is on stderr                      |
"""

import ctypes
import errno
import fcntl
import os
import struct
import sys
from typing import List

# mtio: the kernel headers, linux/mtio.h
MTIOCTOP: int = 0x40086D01      # _IOW('m', 1, struct mtop {short mt_op; int mt_count;})
MTIOCGET: int = 0x80306D02      # _IOR('m', 2, struct mtget)
MTREW: int = 6
MTOFFL: int = 7                 # rewind and unload
MTSETBLK: int = 20
OPERATIONS: dict = {"rewind": [(MTREW, 1), (MTSETBLK, 0)], "eject": [(MTOFFL, 1)]}      # (operation, count)
GMT_BOT: int = 0x40000000
GMT_WR_PROT: int = 0x04000000
GMT_ONLINE: int = 0x01000000
GMT_DR_OPEN: int = 0x00040000   # no tape
NO_MEDIUM: int = 10
BUSY: int = 11
NOT_READY: int = 12

# SG_IO, linux/sg.h
SG_IO: int = 0x2285
DXFER_NONE, DXFER_TO_DEV, DXFER_FROM_DEV = -1, -2, -3
TIMEOUT_MS: int = 20000

# READ / WRITE ATTRIBUTE (SPC), the cartridge memory
READ_ATTRIBUTE: int = 0x8C
WRITE_ATTRIBUTE: int = 0x8D
ATTRIBUTE_BUFFER: int = 8192
ATTRIBUTES: list = [(0x0801, 1, 32), (0x0802, 1, 8), (0x0803, 2, 160)]      # id, format (1 ASCII, 2 text), length


class SG_Header(ctypes.Structure):
    """struct sg_io_hdr"""
    _fields_ = [("interface_id", ctypes.c_int), ("dxfer_direction", ctypes.c_int), ("cmd_len", ctypes.c_ubyte),
                ("mx_sb_len", ctypes.c_ubyte), ("iovec_count", ctypes.c_ushort), ("dxfer_len", ctypes.c_uint),
                ("dxferp", ctypes.c_void_p), ("cmdp", ctypes.c_void_p), ("sbp", ctypes.c_void_p),
                ("timeout", ctypes.c_uint), ("flags", ctypes.c_uint), ("pack_id", ctypes.c_int),
                ("usr_ptr", ctypes.c_void_p), ("status", ctypes.c_ubyte), ("masked_status", ctypes.c_ubyte),
                ("msg_status", ctypes.c_ubyte), ("sb_len_wr", ctypes.c_ubyte), ("host_status", ctypes.c_ushort),
                ("driver_status", ctypes.c_ushort), ("resid", ctypes.c_int), ("duration", ctypes.c_uint),
                ("info", ctypes.c_uint)]


def exitCode(number: int) -> int:
    return {errno.ENOMEDIUM: NO_MEDIUM, errno.EBUSY: BUSY}.get(number, 1)


def _open(device: str) -> int:
    return os.open(device, os.O_RDONLY | os.O_NONBLOCK)


def operate(operation: str, device: str) -> None:
    """Raises OSError if the driver refuses."""
    fd: int = _open(device)
    try:
        for op, count in OPERATIONS[operation]:
            fcntl.ioctl(fd, MTIOCTOP, struct.pack("hi", op, count))
    finally:
        os.close(fd)


def status(device: str) -> dict:
    """
    What the driver knows about the tape, MTIOCGET: `noTape`, `writeProtect`, `beginOfTape`, `density` (the
    SCSI density code of the medium, e.g. 0x44), `blocksize` (0 = variable). EBUSY if the drive works.
    """
    fd: int = _open(device)
    try:
        answer: bytearray = bytearray(48)
        fcntl.ioctl(fd, MTIOCGET, answer)
    finally:
        os.close(fd)
    _type, _resid, dsreg, gstat, _er, _file, _block = struct.unpack("lllllii", answer)
    return {
        "noTape": bool(gstat & GMT_DR_OPEN),
        "writeProtect": bool(gstat & GMT_WR_PROT),
        "beginOfTape": bool(gstat & GMT_BOT),
        "online": bool(gstat & GMT_ONLINE),
        "density": dsreg >> 24 & 0xFF,
        "blocksize": dsreg & 0xFFFFFF,
    }


def notReady(device: str) -> bool:
    """The driver answers neither "ready" nor "no tape": the drive loads or unloads (measured: 10 s and 6 s on an LTO-3)."""
    try:
        answer: dict = status(device)
    except OSError:
        return False
    return not answer["online"] and not answer["noTape"]


def scsi(device: str, cdb: bytes, size: int = 0, data: bytes = b"", timeoutMs: int = TIMEOUT_MS) -> bytes:
    """
    A SCSI command on the tape device (ioctl SG_IO), `size` bytes are read or `data` is written. Raises OSError with
    the reason if the kernel, the HBA or the drive refuses it.
    """
    direction: int = DXFER_FROM_DEV if size else DXFER_TO_DEV if data else DXFER_NONE
    buffer = ctypes.create_string_buffer(data if data else size or 1, len(data) or size or 1)
    command = ctypes.create_string_buffer(cdb, len(cdb))
    sense = ctypes.create_string_buffer(64)
    header = SG_Header(interface_id=ord("S"), dxfer_direction=direction, cmd_len=len(cdb), mx_sb_len=len(sense),
                       dxfer_len=len(data) or size, dxferp=ctypes.cast(buffer, ctypes.c_void_p),
                       cmdp=ctypes.cast(command, ctypes.c_void_p), sbp=ctypes.cast(sense, ctypes.c_void_p), timeout=timeoutMs)
    fd: int = _open(device)
    try:
        fcntl.ioctl(fd, SG_IO, header)
    finally:
        os.close(fd)
    if header.status or header.host_status or header.driver_status & 0x0F:
        raise OSError(errno.EIO, "SCSI command 0x%02x refused: status 0x%02x, host 0x%02x, driver 0x%02x, sense %s" %
                      (cdb[0], header.status, header.host_status, header.driver_status, sense.raw[:header.sb_len_wr].hex()))
    return buffer.raw[:size - header.resid] if size else b""


def serial(device: str) -> str:
    """INQUIRY, VPD page 0x80 (unit serial number)."""
    answer: bytes = scsi(device, bytes([0x12, 1, 0x80, 0, 252, 0]), 252, timeoutMs=2000)
    return answer[4:4 + answer[3]].decode("ascii", errors="replace").strip() if len(answer) > 4 else ""


def attributeData(values: List[str]) -> bytes:
    """The parameter list of WRITE ATTRIBUTE: application name, application version, user medium text label."""
    body: bytes = b""
    for (attrId, fmt, length), value in zip(ATTRIBUTES, values):
        raw: bytes = value.encode("utf-8" if fmt == 2 else "ascii")
        if len(raw) > length:
            raise ValueError("Attribute 0x%04x is longer than %d bytes" % (attrId, length))
        body += struct.pack(">HBH", attrId, fmt, length) + raw.ljust(length, b"\0" if fmt == 2 else b" ")
    return struct.pack(">I", len(body)) + body


def readAttributes(device: str) -> bytes:
    return scsi(device, struct.pack(">BB8xIBB", READ_ATTRIBUTE, 0, ATTRIBUTE_BUFFER, 0, 0), ATTRIBUTE_BUFFER)


def writeAttributes(device: str, values: List[str]) -> None:
    data: bytes = attributeData(values)
    scsi(device, struct.pack(">BB8xIBB", WRITE_ATTRIBUTE, 0, len(data), 0, 0), data=data)      # byte for byte what sg_write_attr sends


def main(args: list) -> int:
    usage: dict = {"rewind": 2, "eject": 2, "readattr": 2, "writeattr": 5}
    if len(args) < 2 or args[0] not in usage or len(args) != usage[args[0]]:
        print("Usage: TapeIoctl.py rewind|eject|readattr <device>, writeattr <device> <name> <version> <label>", file=sys.stderr)
        return 2
    operation, device = args[0], args[1]
    try:
        if operation == "readattr":
            answer: bytes = readAttributes(device)
            for n in range(0, len(answer), 16):
                print(" %02x    %s" % (n, " ".join("%02x" % b for b in answer[n:n + 16])))
        elif operation == "writeattr":
            writeAttributes(device, args[2:])
        else:
            operate(operation, device)
    except OSError as e:
        print(operation + " " + device + ": " + errno.errorcode.get(e.errno or 0, "") + " " + str(e.strerror), file=sys.stderr)
        if operation == "rewind" and e.errno == errno.EIO and notReady(device):
            return NOT_READY
        return exitCode(e.errno or 0)
    except ValueError as e:
        print(operation + " " + device + ": " + str(e), file=sys.stderr)
        return 1
    return 0

# TODO rename this to "TD_Ioctl.py",  It should be a static class not a seperate programm


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

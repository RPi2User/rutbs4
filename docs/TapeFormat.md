# Tape format

**Status: the benchmark exists (`BlockSizeBenchmark`, `benchmark_tape.py`, see SOURCES.md), the format around it does not.**
The pieces that exist today are `CartridgeMemory.format()` (writes a new fingerprint), the block size benchmark
and the default block size `256K` in `TapeDrive`. The result is not stored in the cartridge memory yet.

A tape is **formatted** once, before its first use, and again whenever the operator wants. Formatting
prepares the cartridge for rutbs: it gives the tape its identity and finds out how to write to it fast.

## What a format does

1. **Identity.** A new fingerprint (random UUID) and the version of the backend go into the cartridge
   memory (CM). A format always makes a new fingerprint, even if the chip holds one already.
2. **Block size benchmark.** The bandwidth of the tape is measured for several block sizes and the best one
   is chosen. It goes into the CM too, and later writes use it.

## Rules

- Formatting is **destructive on purpose**: the benchmark writes test data over the tape from its begin. The
  operator knows that; there is no guard against tapes that hold data. It is a request of its own, nothing else
  starts it.
- No zeros are written over the whole tape; only as much as the benchmark needs.
- The tape is rewound afterwards and **never ejected**.
- It is a `Job` runlist like a write, one tape at a time, so the drive is used strictly in order.
- Reading a tape does not depend on the block size (`Read()` uses an 8 MiB buffer and gets each block as it
  was written), only writing does.

## Block size benchmark

Why per tape: the same LTO-3 drive and host reached the full speed with 384K on one make of tape (80 MB/s)
and only 50 MB/s on another make, where 256K is right (operator's measurement). The value belongs to the
cartridge, and probably to the drive it was measured on.

- **Default: `256K`.** It is the first candidate, the reference of the table, and the value used when no
  benchmark ran or none could decide. It is a multiple of 512 (the tar block) and fills the drive buffer well.
- Other candidates: multiples of 64K from 128K up to 512K, then 768K, 1M, 2M, 4M. **128K is the lower limit**
  (HP asks for at least 128 KiB per transfer; on the LTO-8 test drive 64K to 4M were all within the noise of about 10 %,
  so without a limit the pick would be arbitrary). Powers of two alone would miss
  values like 384K. A candidate the driver or HBA refuses (`st(4)`: the driver buffer and the HBA limit the
  block size) is left out of the table.
- Writing is measured, not reading: in variable block mode the block size is fixed by what is on the tape, a read
  with a smaller `bs` fails (`st(4)`), so a read cannot compare block sizes.
- Per candidate: rewind, `dd` for about 30 to 60 s, take the speed `dd` reports. This is long enough for the
  mechanics to reach full speed at least once. The amount is `native_rate` (table below) times the time,
  e.g. about 2.4 GB on LTO-3 and 10.8 GB on LTO-8 for 30 s. It is much less than the tape; nothing is
  written to the end.
- `dd` reads a pipe, so it needs `iflag=fullblock`; otherwise short reads become short tape blocks and the
  numbers mean nothing.
- The data is incompressible (a cipher stream, not zeros): the drive compresses, and zeros would show
  a speed that real, encrypted data never reaches.
- The pick: every block size with at least **90 % of the ideal rate** (table below) is good enough, of
  those the **smallest** is taken, because a smaller block is kinder to the HBA and the driver buffer. If the
  LTO version has no ideal rate, the best measured speed is the yardstick.
  Example (LTO-3, ideal 80 MB/s = 76.3 MiB/s, limit 68.7 MiB/s): 128K 71.2, 192K 70.9, 256K 75, 384K 75,
  512K 72, 1024K 65.9 MiB/s; 128K is the smallest one over the limit and is picked.
- **Warning instead of an error:** if even the best block size stays below 90 % of the ideal rate, the answer
  warns: "only xxx % of the ideal bandwidth is usable. Is this a half height drive or a worn tape?" The best one
  is the yardstick then: the smallest block size within 90 % of the best is picked. Only if nothing could be
  measured, `256K` is used (and the answer says so).
- The answer is the table (block size, MiB/s, share of the ideal rate) and the pick, so the operator sees
  what was measured.

### Ideal transfer rate

Native (uncompressed) rate from the LTO specification, in `E_LTO_Rate` and `Tape.native_rate` (bytes/s).
It is the yardstick: a result near it means the block size is not the limit, a result far below it
points to the host, the HBA or the cable.

| LTO | MB/s | MiB/s |
|-----|------|-------|
| 1   | 15   | 14.3  |
| 2   | 40   | 38.1  |
| 3   | 80   | 76.3  |
| 4   | 120  | 114.4 |
| 5   | 140  | 133.5 |
| 6   | 160  | 152.6 |
| 7   | 300  | 286.1 |
| 8   | 360  | 343.3 |
| 9   | 400  | 381.5 |
| 10  | 400  | 381.5 |

## Cartridge memory

| Attribute | Format | Content                                                                 |
|-----------|--------|-------------------------------------------------------------------------|
| `0x0801`  | ASCII  | application name, `rutbs`                                               |
| `0x0802`  | ASCII  | application version, the backend version as 4 hex digits               |
| `0x0803`  | text   | user medium text label, the fingerprint                                 |
| `0x080B`  | ASCII  | application format version, 16 bytes, proposal: `bs=262144` (block size in bytes). To be checked on the drive |

The CM is written once at the end, when the benchmark is done. A failed write keeps the old values and says why
(`CartridgeMemory.error`).

## Open

- A format that fails halfway has overwritten the tape but the CM still holds the old fingerprint. Probably the
  old fingerprint must be cleared first, so a half-formatted tape is recognised as such.
- How much data per candidate: enough to reach streaming speed (a few seconds), little enough to keep the
  whole benchmark short. To be tried on the drive.
- The drive state machine (see DESIGN.md, "Drives") should be in place before the format asks for the drive.

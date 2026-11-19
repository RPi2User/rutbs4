# Tape format

**Status: planned for the release candidate, not implemented.** The pieces that exist today are
`CartridgeMemory.format()` (writes a new fingerprint) and the fixed block size `256K` in `TapeDrive`.

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

- Candidates: multiples of 64K up to 512K, then 768K, 1M, 2M, 4M. Powers of two alone would miss values
  like 384K.
- Per candidate: rewind, `dd` a fixed amount of data, take the speed `dd` reports.
- The data is incompressible (a cipher stream, not zeros): the drive compresses, and zeros would show
  a speed that real, encrypted data never reaches.
- The pick is the smallest block size within about 5 % of the best speed.
- The answer is the table (block size, MB/s) and the pick, so the operator sees what was measured.

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

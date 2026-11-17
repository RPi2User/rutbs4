# Target Design

What rutbs4 is supposed to become. Decisions are from the architecture review on
2026-11-16; items marked **(proposal)** are not confirmed yet.
For the current state of each source file see [SOURCES.md](SOURCES.md).

## Principles

- The backend is a plain REST server (Flask + Swagger). There is no other interface.
- Keep it simple: shell out to standard tools, no database, no config file on the server.
- **Bring your own security.** The backend speaks HTTP and receives the passphrase in
  clear text. Whoever exposes it beyond a trusted LAN puts HTTPS in front of it.
- We do what the operator asks for. Many small files are slow on tape; that is the
  operator's decision, not ours.
- A tape is written and read as a whole, in one go. Nothing is ever appended.

## Version

One version for backend, tape format and cartridge memory, stored as 16 bit
(`backend/Version.py`): 4 bit major, 4 bit minor, 8 bit bugfix. `4.0.0` = `0x4000` =
`0b0100 0000 0000 0000`.

## Tape layout

```
tape file 0      TOC, state IDLE        the plan: order, sizes, keys
tape file 1..N   the files, in exactly the order of the TOC
tape file N+1    TOC, state COMPLETE    the result: same content plus checksums
```

- The **tape file number** is the position of a file. It is stored in the TOC, and a SCSI
  SPACE command (file marks) jumps to it.
- The order is fixed when the job is created (sorted by relative path). Nothing about it
  depends on timing, so the first TOC can be written before any file is processed.
- The second TOC gives redundancy (a damaged begin of tape does not lose the tape) and is
  the final write test: if it is on the tape, everything before it fits.
- **Tape cannot be changed in place.** Writing at the begin of tape makes everything
  behind it unreadable. The first TOC therefore always says `IDLE`: it is a plan, nothing
  is finished. A tape is good only if a trailing TOC with state `COMPLETE` exists. On a failed job the trailing TOC is
  written with state `FAILED` if the drive still accepts it; if not, the missing trailing
  TOC is the failure marker. With a cartridge memory the failure is noted there as well.
- A tape that already carries a fingerprint is only overwritten after an explicit format.
- Tapes written by tbk3 are not supported.

## Fingerprint and cartridge memory

- Every tape gets a fingerprint (random UUID) when it is formatted. It is stored in clear
  text in the TOC header, so operator and changer can check that the right tape is loaded.
- `Tape.cartridgeMemory` is an optional object for the chip in the cartridge. Reading it
  is attempted; if that fails the tape works without it.
  - Fields: `fingerprint`, `version` (16 bit, the backend that formatted it), write-error flag.
  - `read()` builds the command and fills the fields; `format()` writes a new fingerprint.
  - If the chip already holds a fingerprint, the TOC uses that one, so the chip is not
    rewritten on every format of the tape.
- **(proposal)** Attributes used on the chip (`sg_read_attr` / `sg_write_attr`):
  `0x0801` application name = `rutbs`, `0x0802` application version = version as hex,
  `0x0803` user medium text label = fingerprint. Needs to be checked on real drives.

## Table of content

The TOC keeps the style of the current code: it contains the complete objects, including
every `Command` in the state it had at that moment. A TOC is therefore also the log of
the job; for every file it shows which step failed and why. Its size does not matter.

- Format: JSON.
- **Header**, clear text: timestamp, hostname, thread count, version, state
  (`IDLE` / `COMPLETE` / `FAILED`) and the drive with its tape, which carries the
  fingerprint.
- **Body**, encrypted with the passphrase of the tape: the folders with all their files.
  The cipher used for the body is named in the header.
- Path fields of a file, all needed: `path` (absolute, used by `dd`), `relPath` (to
  restore the directory tree), `parent` (differs from `context` for files in sub
  directories), `context` (the input directory of the request).
- `id` of a file is its tape file number.
- The first TOC is frozen before anything ran, the trailing one after everything ran.
- Key hierarchy: passphrase (from the API request) → TOC body → key and IV of each file.
  Every file has its own pair; all pairs are protected by the passphrase alone.
  A wrong passphrase shows as a body that is not valid JSON.
- The clear-text header must never contain key material. The drive snapshot in the header
  therefore must not carry the file the drive is working on.
- Every final TOC is also stored in the TOC directory of the backend (default `/opt/rutbs`)
  as `YYYYMMDD_hhmmss_<fingerprint>.json`. This loose collection answers which tape holds a
  file, and a passphrase can be tested against it without loading the tape.
- **(proposal)** Container: `{"header": {…}, "body": "…"}` in one JSON document, see
  `examples/toc_proposal_tape.json`. The body is the output of the cipher named in the
  header. Encrypted bytes are binary and JSON cannot hold them, so they are written in
  base64; base64 is only that text form, not the protection.

A slim TOC with only the fields needed for a restore is an idea for a later version;
`examples/toc_proposal_plain.json` shows it next to `examples/toc_backend.json`.

## Job

A job is the complete run list of one request, for example a write:

```
rewind → format → write TOC → per file: checksum → encrypt → write → write TOC → rewind → eject
```

- The run list fixes the tape order; the final TOC is the result of the job.
- Everything that can run in parallel does, limited by the thread limit of the host.
  A drive handles one command at a time, strictly in the order of the run list.
  Typically many checksums run first, encryption follows, and finished files wait in
  the spool until the drive takes them.
- If a step fails the job is aborted: no further file is written, the trailing TOC is
  written with state `FAILED`, the tape is rewound.
- Jobs live in memory. A job that is interrupted by a restart of the backend has failed.
- A write is rejected up front if the files do not fit the native capacity of the tape.
  Nothing is spread over several tapes.
- Read-back verification after a write is optional and off by default.

There is **one queue for the whole host** (`backend/Job.py`). The host accepts several
jobs at once, for example one per drive, and the single queue is what keeps the thread
limit. An entry is started when it is ready and resources are free. Resources are used up
when the number of running commands equals the thread limit, or when the drive an entry
needs is already busy.

The entries of one job share a runlist id. That id is what gets aborted on a failure, and
what a client polls for progress. Closing steps (trailing TOC, rewind) are marked so they
still run after an abort.

## File

The file is the core object. It goes through every phase itself:

| Phase | Meaning |
|-------|---------|
| `File.Validate()` | create my checksum |
| `File.Encrypt()` | encrypt me into the spool |
| `File.Write()` | write me to tape |
| `File.Read()` | restore me from tape |
| `File.Decrypt()` | decrypt me |
| `File.Validate()` | check that I am still myself |
| `File.Get()` | fetch me from an S3 bucket — future |

Each phase only prepares one `Command` and hands it to the job, and returns the job entry
id so the next phase can depend on it. The file derives its state from those entries.
There is no second, blocking way to run a phase. The phases are implemented in
`backend/File.py`; `Validate()` creates the checksum, and compares to it when there is one.

- The relative path of a file is kept, so a directory tree is restored 1:1.
  Sub directories are scanned recursively; the files are sorted by relative path, which is
  the tape order.
- Restored metadata: modification time and permissions.
- Restoring a single file: read the TOC, jump to the tape file number, read that one
  file, rewind and eject, report success or not-found.

## Spool and paths

- The host knows its mounts so that input, output and spool can be placed deliberately.
- Input and output path arrive with the API request. A request is answered with an error
  until it is complete; nothing is guessed.
- Every job gets its own spool directory:
  `<mount>/rutbs-spool/<epoch>_<fingerprint>/` with the TOC, the checksum list and the
  encrypted files. It is removed when the job is done. The mount must be a real mount
  point (`backend/Mount.py` finds them with `findmnt`), a plain directory is refused.
- Encrypted files in the spool are named after their tape file number (`0001.crypt`),
  because two files in different directories may share a name.

## Security

- Passphrase per tape, supplied by the operator with the request, never stored.
  It is the master key: it encrypts the TOC body, and with it the keys of all files.
- Every file is encrypted with its own random key and IV.
- Secrets are passed to `openssl` through the environment, not the command line, and are
  not part of any status output.
- All cipher modes stay available so new ones can be added and old tapes stay readable.

## Drives

- The backend finds the drives itself and reports vendor, model, serial, device paths and
  state. One implementation, run at start and on request.
- A drive is identified by the **id of its logical unit** that the kernel reads from the
  device identification (SCSI INQUIRY VPD page 0x83) and publishes in sysfs as `wwid`
  (`naa.50050763121a839e`). It is not the serial number. A drive with two SAS cables shows up
  as two `sg` and two `nst` devices with the same `wwid` (the ports differ): that is ONE
  `TapeDrive`, `TapeDrive.paths` lists all pairs and the first one is used. `TapeDrive.id`
  is the key the Job uses, so a drive never gets two commands at once, whichever path.
- **A drive is never hidden.** Whenever the kernel made a `/dev/nstX` for it, it is listed.
  If it cannot be proven that two paths are one drive (no `wwid`, or the same `wwid` with
  a different vendor / model), they are listed as two, with a warning. Showing a drive twice
  is better than not showing it.
- **The drive decides whether it can take an order.** Before every job step the drive is
  asked, over SCSI, whether it is able to accept it, and the state machine acts on the
  answer. That is what keeps a drive that is listed twice (or used by another process) from
  getting two orders at once; the backend keeps no bookkeeping for it. The steps stay small
  and atomic for this reason. Open: which query shows reliably that the drive is busy on its
  other path (TEST UNIT READY, or RESERVE / RELEASE); to be tried on the drive while a write
  runs. Today `TapeDrive` only looks at the state of its own `Command`, there is no
  query to the drive yet.
- A `TapeDrive` does four things: rewind, eject, write a data stream with `dd`, read a data
  stream with `dd`. Everything else is optional: reading the cartridge memory, seeking
  (one file forward / backward, file n), formatting. Eject is never part of a test run.
- SCSI only: the code sends SCSI commands (`sg_raw`) and uses `dd` on the `nst` device. It
  does not use `mt`; the operator may. Horizon: a Python SCSI library instead of `sg_raw`.
- Position: the backend only knows "at begin of tape" or "not". It rewinds itself before
  it starts a job.
- Block size belongs to the tape and is stored in the TOC header. Default `256K`.
  A benchmark that helps the operator choose is planned.

## Host and REST API

- The host has a stable fingerprint, so a frontend can recognise it and send the matching
  configuration. It is read from a machine id file.
- The backend has exactly two command line arguments. Everything else is configured at run
  time, the port is fixed (5533).

  | Argument | Default |
  |----------|---------|
  | TOC directory | `/opt/rutbs` |
  | machine id file | `/etc/machine-id` |
- Configuration (paths, thread limit, …) is set at run time through the API and held in
  memory. The frontend is responsible for providing it.
- Long operations do not block the request: `POST` returns a job id, the progress is polled.
- One status request returns everything a frontend needs for its graphs (CPU, memory,
  load, mounts, drives, jobs), each response with a timestamp. Parts can be requested
  separately.
- GUI and CLI clients live outside this repository.

## Open points

1. Whether the manufacturer's medium serial number (chip attribute `0x0401`, read-only)
   should be used as fingerprint when the chip is readable. It would never need writing.
2. The TOC container is implemented as header and encrypted body in one JSON document
   (body as base64 text). To confirm, or switch to the encrypted body as raw bytes behind
   the header.

## Next steps

Done: tape order follows the queue; a failure aborts its run list; every file has its own
key; secrets are kept off the command line; TOC with version, fingerprint, state, encrypted
body, reading from text and TOC directory; recursive scan in tape order, mounts and spool
directory; the file phases (`Validate`, `Encrypt`, `Write`, `Read`, `Decrypt`) on the queue.

1. TOC: reading it back from tape (needs the drive, see 3).
2. Restore of a whole folder: build the files from the TOC (a `File` needs an existing
   file today), `Folder.queueRestore()`, restore of metadata. Needs the positioning of 3.
3. TapeDrive: the four functions as job phases (`Rewind()`, `Eject()`, `Write()`, `Read()`,
   queued in tape order), the trailing TOC, remove the old `write()` / `read()` /
   `writeTOC()` / `format()`. Optional: seek by tape file number with the SCSI SPACE
   command. Drive discovery is done (`TD_Pool`). Needs the drive to verify.
4. Host and REST API on the new core; then remove `write_folder_to_tape.py`.
5. Cartridge memory. Needs hardware.

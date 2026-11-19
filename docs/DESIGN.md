# Target Design

What rutbs4 is supposed to become. Decisions are from the architecture review on
2026-11-16; items marked **(proposal)** are not confirmed yet.
For the current state of each source file see [SOURCES.md](SOURCES.md).

## Principles

- The backend is a plain REST server (Flask + Swagger). There is no other interface.
- Keep it simple: shell out to standard tools, no database, no config file on the server.
  (A database for the jobs is being considered, see "Todo: a database for the jobs".)
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
tape file 0      TOC, state IDLE        order, sizes, keys, checksums
tape file 1..N   the files, in exactly the order of the TOC
tape file N+1    TOC, state COMPLETE    the same content, plus the result of the writing
```

- The **tape file number** is the position of a file. It is stored in the TOC, and a SCSI
  SPACE command (file marks) jumps to it.
- The order is fixed when the job is created (sorted by relative path). Nothing about it
  depends on timing.
- **Both TOCs are equivalent.** The drive idles until it could, in theory, write both of them,
  that is until the checksum of every file is known. Only then the first TOC is written. The two
  differ in the header state and in the log of the commands, nothing else (a reader compares them
  with `TableOfContent.differences()`). If a checksum fails, the tape is not touched.
- The second TOC gives redundancy (a damaged begin of tape does not lose the tape) and is
  the final write test: if it is on the tape, everything before it fits.
- Reading: the first TOC is read at the begin; the last one is reached with SPACE to the end of
  the data, two file marks back, one forward. A tape without the last TOC is incomplete (the write
  did not finish); a restore refuses it unless the TOC directory holds a copy.
- **Tape cannot be changed in place.** Writing at the begin of tape makes everything
  behind it unreadable. The first TOC therefore cannot be completed afterwards: it says `IDLE`
  and holds everything that is known before the first file is written. A tape is good only if a trailing TOC with state `COMPLETE` exists. On a failed job the trailing TOC is
  written with state `FAILED` if the drive still accepts it; if not, the missing trailing
  TOC is the failure marker. With a cartridge memory the failure is noted there as well.
- A tape that already carries a fingerprint is only overwritten after it is explicitly registered anew
  (not implemented yet; today every write starts at the begin of tape).
- Tapes written by tbk3 are not supported.

## Fingerprint and cartridge memory

- Every tape gets a fingerprint (random UUID) when it is registered. Registering writes the chip only, never the tape. It is stored in clear
  text in the TOC header, so operator and changer can check that the right tape is loaded.
- `Tape.cartridgeMemory` is an optional object for the chip in the cartridge. Reading it
  is attempted; if that fails the tape works without it.
  - Fields: `fingerprint`, `version` (16 bit, the backend that registered it), write-error flag.
  - `read()` builds the command and fills the fields; `register()` writes a new fingerprint.
  - If the chip already holds a fingerprint, the TOC uses that one, so the chip is not
    rewritten on every registration of the tape.
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
- The first TOC is made when all checksums are known and before the first file is written, the
  trailing one after everything ran.
- **Unencrypted request** (`unencrypted=true`, only without a passphrase): the TOC removes all
  encryption (`removeEncryption()`), so `body_cipher` is `NONE`, the body is plain JSON, the files
  have mode `NONE` and no key. The tape then holds the original files and a readable TOC (file names,
  paths, checksums). A request without passphrase and without `unencrypted` is refused with
  "Passphrase for encryption required"; passphrase and `unencrypted` together are refused as well.
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
all checksums → rewind → write TOC → per file: encrypt → write → write TOC → rewind → eject (on request)
```

This is `backend/WriteJob.py`. A tape is not formatted (see "Milestone and what comes after").
The restore is `backend/ReadJob.py`, in two steps because the passphrase is asked after the tape was
seen:

```
open():   rewind → read first TOC → to the end, 2 file marks back, 1 forward → read last TOC → rewind
queue():  open and compare both TOCs → skip first TOC → per file: read → decrypt → checksum → rewind
```

The checksum of each file is compared with the one in the last TOC. A restore is refused up front if
the two TOCs disagree about the plan, if the writing job failed, or if a target file exists.

- The run list fixes the tape order; the final TOC is the result of the job.
- Everything that can run in parallel does, limited by the thread limit of the host.
  A drive handles one command at a time, strictly in the order of the run list.
  Checksums run first and the drive waits for all of them (`Job.Add(waitFor=...)`), encryption
  follows, and finished files wait in the spool until the drive takes them.
- If a step fails the job is aborted: no further file is written, the trailing TOC is
  written with state `FAILED`, the tape is rewound, it is not ejected.
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
still run after an abort. A step can have a `prepare` hook that runs right before it starts:
the trailing TOC is made there, when the results of all files are known.

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
- A `TapeDrive` does four things, as steps in the Job queue: `Rewind()`, `Eject()`, `Write()` (a
  data stream with `dd`), `Read()` (a data stream with `dd`). Reading also needs seeking, which exists as
  `Space(files)` and `SpaceEnd()` (SCSI SPACE over file marks). Everything else is optional: reading the
  cartridge memory, formatting. Eject is never part of a test run.
- **Reading rules, learned on the real drive:** `Read()` must not use `dd iflag=fullblock` (it reads on
  behind the file mark after a short last block and returns several tape files as one). And no `dd` may read
  at the end of the data: the kernel driver (`st`) latches that and answers every later read with an I/O
  error, even after a rewind with `sg_raw`, until the driver itself is repositioned (`mt rewind` by the
  operator). Because of that the last TOC is reached by SPACE, never by reading until it fails.
  Open: whether `Rewind()` should go through the driver so that this cannot happen at all.
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

## Milestone and what comes after

**Milestone 1 (2026-11-17/18): writing works.** One `WriteJob` writes a folder to a real LTO-8
tape: rewind, first TOC, every file (checksum, encryption, write), last TOC, rewind, and an
eject only on request. Tested by hand on the drive, then corrected: the job now does all
the steps itself, `TapeDrive` has only its four steps, `__str__` is always `indent=2`, the
checksum defaults to SHA256.

**Milestone 2 (2026-11-18): restoring works.** `ReadJob` restores a whole tape: both TOCs, the
passphrase, `Read` → `Decrypt` → `Validate` per file, rewind. Tested on the real LTO-8: a tape with
1.4 GB in 15 files, byte-identical (`diff -r`) after the round trip, tape rewound and not ejected.
Found on the way: the `dd iflag=fullblock` read, the end-of-data latch of the `st` driver (see "Drives") and
a test tape without last TOC (restored with the copy from the TOC directory).

Everything below comes after the milestones and is postponed:

1. **Restore, the rest.** Modification time and permissions (not in the TOC yet), restoring a single file
   (jump to its tape file number, the seeking exists), emptying the spool while the restore runs.
2. **Cartridge memory before the fingerprint.** Read the chip (LTO-CM) first; if it holds a
   fingerprint the TOC uses it, else a new one is made and set. See "Fingerprint and cartridge memory".
3. **Registering a tape in the cartridge memory.** This is NOT a format in the classic sense:
   no zeros are written over the tape. The tape is only registered (fingerprint, version in the
   chip). The old `format` step of the run list is therefore gone for now.
4. **The REST API** on the new core; then remove `write_folder_to_tape.py` and `read_tape_to_folder.py`.
5. The drive is asked whether it can take a step before each one (see "Drives").
6. Spool: hold back the encryption while the tape is slower, delete spool files after they were written.
7. System commands: every command goes through the Job system, see "Todo: system commands".
8. A database for the jobs, see "Todo: a database for the jobs".

## Todo: system commands

Decided on 2026-11-18, **not implemented**. All commands go through the Job system, so there is one
place for deadline, kill and log. Small requests (a few random bytes, the size of a file, a SCSI
query) must not wait for the thread limit and must not block the caller for long, much like the
deadlines known from real-time systems: the Job system grants such a command direct execution
because it may kill it once the deadline is over.

- New call `Job.Run(cmd, deadlineMs=2000)`. It runs the command at once in the caller's thread,
  takes no slot of the thread limit, kills it when the deadline is over and returns the finished
  `Command`. It is not a flag of `Job.Add()`: it must work inside constructors and inside
  `prepare` hooks, which run under the Job lock, so it never waits for the scheduler and never
  holds the lock while waiting.
- The default deadline is **2 s**. Measured: `openssl rand`, `stat`, `findmnt` take 2 to 4 ms and
  the SCSI queries INQUIRY, MODE SENSE and TEST UNIT READY about 3.5 ms on the idle drive.
- The deadline is wall-clock time, not CPU time: a command that waits on a hung mount or a busy
  drive uses almost no CPU and would never be caught. `RLIMIT_CPU` can be a second guard.
- The folder scan (`find`) is a system job as well, with a deadline of **60 s**.
- Only small things are system commands. Never rewind, eject, `dd`, checksum or encryption. On a
  drive only read-only SCSI queries; they may run while the drive works on its queue, which is also
  the way to ask the drive before a step (see "Drives").
- **New state:** a command that was killed because the system was not fast enough gets its own
  state (working name `KILLED`, "deadline exceeded") in the state machine of `Command` / `Job`,
  distinct from `FAILED` (exit code not 0). Open: whether a runlist treats it like `FAILED`
  (probably yes).
- The system commands get a registry of their own, see the next section.
- Places to convert: `Key` (two `openssl rand`), `File.readSize()` (`stat`), `Mount` (`findmnt`),
  `Folder` (`find`), `TapeDrive` (INQUIRY, MODE SENSE and its retry), and the TOC encryption, which
  uses `subprocess.run` because `Command` has no stdin yet. `Command` needs stdin first (the
  passphrase stays in the environment).

## Todo: a database for the jobs

Not decided, **not implemented**. The jobs (and the system commands) with their metadata are
stored in an SQL database; the author has nothing against it. Today the jobs live in memory and a
job that is interrupted by a restart has failed.

- This breaks the principle "no database". If it is adopted, that line changes.
- Suggestion: SQLite, because it is part of Python and needs no server. To decide: which database,
  what exactly is stored, how long.
- What would change: jobs and their history survive a restart, a frontend can list finished jobs,
  and the system commands get their registry without growing the memory.
- Never store secrets: the environment of a `Command` (the key of a file) stays out. The command
  line is fine, it holds the IV but never a key or passphrase.


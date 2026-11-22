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
- Reading: from the begin to the end, nothing is seeked or skipped: first TOC, the files, last TOC. The first TOC
  says how many files follow, so nothing is read behind the last one. **The last TOC decides** whether the files were
  restored; without it, or if it is not `COMPLETE`, the tape is not valid. There is no other source for it. The first TOC only says
  which tape it is and whether something happened to it.
- **Tape cannot be changed in place.** Writing at the begin of tape makes everything
  behind it unreadable. The first TOC therefore cannot be completed afterwards: it says `IDLE`
  and holds everything that is known before the first file is written. A tape is good only if a trailing TOC with state `COMPLETE` exists. On a failed job the trailing TOC is
  written with state `FAILED` if the drive still accepts it; if not, the missing trailing
  TOC is the failure marker. With a cartridge memory the failure is noted there as well.
- **No overwrite protection** (decided 2026-11-22): a write order starts at the begin of the tape, whatever is on it. The operator can read
  the TOC first; an important tape gets its write protect switch set.
- Tapes written by tbk3 are not supported.

## Fingerprint and cartridge memory

- Every tape gets a fingerprint (random UUID) when it is formatted (see [TapeFormat.md](TapeFormat.md)). The fingerprint itself is written to the chip only. It is stored in clear
  text in the TOC header, so operator and changer can check that the right tape is loaded.
- `Tape.cartridgeMemory` is an optional object for the chip in the cartridge. Reading it
  is attempted; if that fails the tape works without it.
  - Fields: `fingerprint`, `version` (16 bit, the backend that registered it), write-error flag.
  - `read()` builds the command and fills the fields; `register()` writes a new fingerprint.
  - If the chip already holds a fingerprint, the TOC uses that one, so the chip is not
    rewritten on every registration of the tape.
- **(proposal)** Attributes used on the chip (READ / WRITE ATTRIBUTE, ioctl `SG_IO` on `nstX`):
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
- `id` of a file is its tape file number (it counts every file; an empty plain file has no tape file, `dd` writes nothing and
  no file mark, so writer and reader both leave it out).
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
open():   rewind → read first TOC → rewind
queue():  rewind → read first TOC → per file: read → decrypt → checksum → read last TOC → compare both TOCs → rewind
```

The checksum of each file is compared with the one in the TOC as soon as the file is decrypted. Whether the job is good is
decided by the last TOC: the job is `FAILED` if it is missing, damaged, disagrees about the plan or is not `COMPLETE`. A restore is
refused up front if the first TOC says `FAILED` or a target file exists.

- The run list fixes the tape order; the final TOC is the result of the job.
- Everything that can run in parallel does, limited by the thread limit of the host.
  A drive handles one command at a time, strictly in the order of the run list.
  Checksums run first and the drive waits for all of them (`Job.Add(waitFor=...)`), encryption
  follows, and finished files wait in the spool until the drive takes them.
- If a step fails the job is aborted: no further file is written, the trailing TOC is
  written with state `FAILED`, the tape is rewound, it is not ejected.
- Jobs live in memory, there is no database. The backend is restarted only outside of backup
  jobs; a job that is interrupted by a restart has failed.
- A write is rejected up front if the files do not fit the native capacity of the tape.
  Nothing is spread over several tapes.
- Read-back verification after a write is optional and off by default.

There is **one queue for the whole host** (`backend/Job.py`). The host accepts several
jobs at once, for example one per drive, and the single queue is what keeps the thread
limit. An entry is started when it is ready and resources are free. Resources are used up
when the number of running commands equals the thread limit, or when the drive an entry
needs is already busy.

The registry (`Job.queue` and `Job.urgent`) is not archived. A new write or read request replaces the
registry of the previous request **of the same drive**; the frontend archives finished runs if it wants to
(the output is verbose enough for that). Every entry carries the id (wwid) of the drive of its request
(`Entry.drive`, set by the job also for checksums and closing steps), so the API calls
`Job.Flush(killRunning=False, drive=id)` and a running request on another drive is not touched.

A queued command has no deadline: a running step is finished or stopped by the operator. Two requests
are planned for that, **abort** (finish the current step, then end peacefully) and **kill** (terminate),
both as API requests. Only urgent commands are killed by the system, see "System commands".

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
- **The drive is always mapped by a state machine, and the drive decides whether it can take an
  order.** Nobody can prevent another process from holding a lock on the drive (or the second path of a
  drive that is listed twice). Therefore the drive is asked over SCSI for its state before every action,
  except trivial ones (reading the cartridge memory, a status query), and the state machine acts on the
  answer. The backend keeps no bookkeeping for it; the steps stay small and atomic for this reason.
  Not implemented yet. Open: which query shows reliably that the drive is busy on its other path
  (TEST UNIT READY, or RESERVE / RELEASE); to be tried on the drive while a write runs. Today `TapeDrive`
  only looks at the state of its own `Command`.
- **The OS only has to give:** the list of the `nstX` devices, rewind, eject, `dd if=/dev/nstX`, `dd of=/dev/nstX`
  (decided 2026-11-22). Everything else is optional and must never stop a job: how many individual drives there are, the fingerprint
  in the chip, the LTO version, the position. The LTO version and the size come from the operator if need be
  (`tapeOverride()`). A tape the drive does not describe is `UNKNOWN`, and that is no reason to refuse a job.
- A `TapeDrive` does four things, as steps in the Job queue: `Rewind()`, `Eject()`, `Write()` (a
  data stream with `dd`), `Read()` (a data stream with `dd`). Eject happens on request only and is never part of a test run.
- **Rewind and eject go through the `st` driver** (`backend/TapeIoctl.py`, ioctl on `nstX` opened with `O_NONBLOCK`), not through
  `sg_raw` (decided 2026-11-22, it replaces "SCSI only"). `mt` is not used. Reasons, measured on an LTO-3:
  one read at the end of the data makes the driver (`st`) answer every later read with an I/O error; its own rewind clears that, a rewind
  with `sg_raw` does not. And a rewind answers at once, so it is **the query of the state machine**:

  | Answer of `rewind(nstX)` | Meaning |
  |--------------------------|---------|
  | ok | a tape is there and it is at its begin |
  | `ENOMEDIUM` → `NO_TAPE` | no tape |
  | `EBUSY` → `BUSY` | somebody else has the device open, e.g. a running `dd` |
  | `EIO`, and `MTIOCGET` says neither "online" nor "no tape" → `NOT_READY` | it loads or unloads a tape (measured: 10 s and 6 s) |

  Not covered: the second path of a drive with two cables has its own `nstX` device. A `dd` opens the device
  blocking and waits 2 minutes for a tape if there is none (123 s measured), so every job rewinds first.
- **Reading rules, learned on the real drive:** `Read()` must not use `dd iflag=fullblock` (it reads on
  behind the file mark after a short last block and returns several tape files as one). Writing uses `dd conv=nocreat`: if the drive
  is gone `dd` must fail and not make a regular file `/dev/nstX` in memory. No `dd` may read at the end of the
  data (see above). The buffer of `dd` must be at least as big as the block that was written and not bigger than the HBA allows: on an
  `aic79xx` 4M works, 8M does not (`EBUSY`); a smaller buffer than the block fails with `ENOMEM`. Therefore 256K, or the block size of the TOC header if that is
  bigger (256K as tapes up to 2026-11 have such blocks); the TOC itself is written in blocks of 128K, or of the block size of the drive if that is smaller.
- Position: the backend only knows "at begin of tape" or "not". It rewinds itself before
  it starts a job.
- **Everything else about a drive is an ioctl on `nstX`, too** (decided 2026-11-22, there is no sg3_utils, no `mt` and no `/dev/sgX` any more;
  the number of an `sg` device changes with every new disk): tape inserted, write protect and the density code
  with `MTIOCGET`, serial and cartridge memory with `SG_IO`; vendor and model come from sysfs. The LTO version is the
  standardized density code (0x44 = LTO-3; tested with an LTO-3 drive, the codes of the other generations are from the specification), not the medium type of MODE SENSE, which differs between vendors. A drive that does not
  answer within 2 s is given up (the question runs in a thread), and what it does not tell is `UNKNOWN`.
- **A rewind also sets the variable block mode** (`MTSETBLK 0`, decided 2026-11-22). A fixed mode (set by `stinit`, `mt setblk` or
  another program) survives a rewind (measured on the LTO-3 with 512 bytes): the block size of `dd` has no effect then, and a file or
  TOC that is no multiple of it fails with `Invalid argument` in the middle. Only LTO is promised; a drive that refuses the switch
  fails the rewind, before anything is written. It is part of the rewind ioctl, not a new interface of the OS.
- Block size belongs to the tape and is stored in the TOC header. Default `128K` (decided 2026-11-22: it is measured that it costs nothing, see TapeFormat.md), `64K` only if the drive takes nothing bigger.
- **Block size benchmark (wanted for the release candidate):** a tape is formatted once and the format measures
  the bandwidth for several block sizes and keeps the best in the cartridge memory. The block size depends on
  the cartridge, not only on the drive. See [TapeFormat.md](TapeFormat.md).

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
3. **Format a tape**, see [TapeFormat.md](TapeFormat.md): fingerprint and version into the cartridge memory,
   plus the block size benchmark. No zeros are written over the whole tape, but the benchmark is destructive
   on purpose. The old `format` step of the run list is gone: a format is a request of its own.
4. **The REST API** on the new core; then remove `write_folder_to_tape.py` and `read_tape_to_folder.py`.
5. **Drive state machine.** The drive is asked for its state before each step (see "Drives"). Next big item.
6. Spool: hold back the encryption while the tape is slower, delete spool files after they were written.
7. System commands: done, see "System commands". What stays: `Host` (REST layer, still on the old `tbk`) has its own `subprocess.run` calls until it is rebuilt on the new core.
8. Abort and kill of a running job as API requests (see "Job").
9. **(RC)** The block size benchmark inside the format (see 3).

## System commands

Implemented on 2026-11-19, replacing the plan of 2026-11-18 (`Job.Run()` in the caller's thread, no flag).
**Only `Job` starts a command**; `Command` describes and observes a process and has no `wait()`.
There is one place for start, deadline, kill and log.

- `Job.Add(cmd, urgent=True)`: the `Entry` constructor starts the command as its last step
  (`startAfterCreate`), so there is no wait for the scheduler tick (500 ms). An urgent Entry takes no
  slot of the thread limit and stands alone: no tape, parent, runlist or `prepare`.
- `Job.Run(cmd, deadlineMs=2000)` is `Add(urgent=True)` plus the wait. It returns the finished `Command`.
- Urgent Entries live in their own list (`Job.urgent`), never in the queue, so `Job.Run()` works inside
  constructors and `prepare` hooks (they run under the Job lock) without a nested scheduler pass. The list
  keeps the last 200 finished Entries (`Job.URGENT_KEEP`), `Job.Registry()` shows both lists.
- The deadline is checked by whoever looks at the Entry (`Job.Get()`, `Job.Refresh()`, so also the
  scheduler thread): SIGTERM, 100 ms later SIGKILL, 100 ms later the Entry is given up. The Entry gets the
  state `KILLED` (not `FAILED`), `Command.killed` is set and `status_msg` says why. A process in
  uninterruptible sleep (hung mount, busy drive) survives SIGKILL: `Job` never waits for it.
  A `KILLED` parent fails its children like a `FAILED` one.
- Deadlines are wall-clock and conservative: **2 s** by default (measured: `openssl rand`, `stat`,
  `findmnt` 2 to 4 ms), 60 s for the `find` of a `Folder` and the `stat` of a `File`. The mechanism is not for the regular case: what is needed often belongs in a small
  list that is built at start and refreshed periodically. A flood of urgent commands is felt by the
  host; the design accepts that.
- Only small things are system commands, and only on disks and file systems (decided 2026-11-22). Nothing about a tape drive is
  urgent: rewind, eject, `dd` and the cartridge memory are steps of the queue of the drive, and what is asked about a drive without
  moving the tape (see "Drives") is an ioctl in the process itself.
- Converted: `Key` (`openssl rand`), `File.readSize()` (`stat`), `Mount` (`findmnt`), `Folder` (`find`),
  and the TOC cipher.
- `Command(..., stdin=bytes)`: the TOC goes through `openssl` as stdin, the passphrase as environment.
  A thread writes the input, so a big input and a big output cannot block each other. The input is
  released once the process has it and only its size is shown (it holds the keys); without `stdin`
  the input is `/dev/null`. The TOC encryption is converted (`TableOfContent._openssl`, raw output).
- `Host.drive_eject()` does not wait for the eject. It answers `202 Issued Eject Command to TapeDrive.`
  and the drive state shows whether it worked (it still calls the old `tbk` drive; `UT_Host` uses fake drives).

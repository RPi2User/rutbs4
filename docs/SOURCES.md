# Source Overview

One short section per source file: what it does, how to use it, what to watch out for.
State: working tree of 2026-11-18. Where the project is heading: [DESIGN.md](DESIGN.md).

## Big picture

rutbs4 writes files to LTO tape. Everything is done by shelling out to standard tools
(`dd`, `openssl`, `sg_raw`, `find`, `stat`); Python only builds the command strings and
tracks their state.

```
WriteJob / ReadJob               <- one write / restore request: the whole run list
  ├─ TapeDrive ── Tape           drive + inserted tape (found by TD_Pool)
  ├─ Folder ── File              what to write
  │             ├─ Checksum
  │             └─ Encryption ── Key
  ├─ Spool ── Mount              where the encrypted files wait
  ├─ TableOfContent              JSON description, first and last file on tape
  └─ Job                         runs the queued Commands
All of the above use Command (subprocess wrapper); only Job starts one.
```

There are two generations of code in the repository:

| Status | Files |
|--------|-------|
| **Current**, importable, unit tests pass | `Version`, `Command`, `Checksum`, `Encryption`, `File`, `Folder`, `Spool`, `Mount`, `Job`, `Tape`, `TapeDrive`, `TD_Pool`, `TableOfContent`, `WriteJob`, `ReadJob`, `write_folder_to_tape.py`, `read_tape_to_folder.py` |
| **To be ported**, not importable | `Host`, `rbs_backend.py` — the REST layer. Still written against the package `tbk`, which no longer exists. `Response` belongs to it. |

Conventions used by all current classes:

- `_asdict()` returns a JSON-ready dict, `__str__()` returns it as a JSON string,
  always `json.dumps(..., indent=2)`.
- Creating an operation (`Checksum.create()`, `Encryption.encrypt()`, `File.Write()`) only
  **builds** the `Command`. `Job` starts it. `File` hides the lower classes: it queues their
  commands and derives its state from the Job entries.

---

## backend/

### Version.py

The backend version in one place. `Version.text()` → `"4.0.0"`, `Version.word()` → the
16 bit value `0x4000` (4 bit major, 4 bit minor, 8 bit bugfix), `Version.fromWord()` back.

### Command.py

Wrapper around one shell command (`subprocess.Popen`, `shell=True`). Base of everything else.

- `Command(cmd, filesize=-1, raw=False, env=None, stdin=None)` — does not start anything.
- `env` adds environment variables. Use it for secrets: they do not appear in `ps` or in
  `_asdict()`.
- `Command.quote(path)` wraps a path in single quotes; use it for every path in a command.
- `stdin` (bytes) is written to the standard input by a thread and released once the process has
  it, so a second run needs a new `Command`; only its size (`stdinSize`) is shown. Without `stdin`
  the input is `/dev/null`.
- `start()` runs it in the background, but only `Job` calls it. There is no `wait()`: use
  `Job.Add()` or `Job.Run()`. `kill()` sends SIGTERM, 100 ms later SIGKILL, then gives up
  (`killed` is set by `Job` when a deadline was missed). `reset()` clears the results,
  `status()` refreshes all fields.
- Results: `stdout` / `stderr` (list of lines), `exitCode` (`-1` = not finished), `running`,
  `didRun`.
- `raw=True` stores the output as one hex string in `stdout[0]`. Output that is not valid
  UTF-8 is switched to hex automatically.
- While running, `/proc/<pid>/io` is read into `io` (progress information for `dd`).
  `filesize` is only carried along so a frontend can compute progress.

Notes:
- The command is prefixed with `exec`, so only one simple command works. Wrap anything
  with `;`, `&&` or pipes in `sh -c '...'`.
- `quiet` defaults to `True`; set it to `False` to print the command on start.

### Checksum.py

Checksum of one file via `openssl <md5|sha256|sha512> -r`.

- `Checksum(file_path, type=SHA256)`, `setType(type)`.
- `create()` prepares a new calculation, `validate(target)` prepares a comparison against a
  known value; `Job` runs it and `_status()` stores the result in `value`. Each builds a new
  `Command`, so the type can be changed at any time and the Job queue never sees the same
  object twice.
- States (`ChecksumState`): `IDLE`, `CREATE`, `VALIDATE`, `MISMATCH`, `ERROR`.
- `ChecksumType.NONE` turns `create()` into a no-op.

Notes:
- `ERROR` is permanent, there is no way to reset it.
- `_status()` is "private" by name but is the method callers use to collect the result
  after the command was run by `Job`.

### Encryption.py

File encryption via `openssl aes-{128,256}-{cbc,ctr} -pbkdf2`.

- `Key(length=KeyLength.medium)` generates a random key and IV with `openssl rand`
  (two urgent Job entries, `Job.Run`). Both are hex strings in `value` / `iv`.
- `Encryption(key, mode=E_Mode.AES256CBC)`.
- `encrypt(path, target="")` prepares `path` → `target`, by default `path + ".crypt"`;
  `decrypt(path, target="")` prepares the reverse (by default it strips the last extension).
  The result path is in `targetPath`, the new command in `cmd`.
- `E_Mode.NONE` turns both into no-ops. States (`E_State`): `IDLE`, `ENCRYPT`, `DECRYPT`, `ERROR`.

Notes:
- The key is used as a passphrase (`-pass env:RUTBS_KEY`), not as raw key. openssl derives
  the real AES key from it, so `KeyLength` does not have to match the AES mode.
- The key is not on the command line, but `Key._asdict()` still prints key and IV.

### File.py

One file on disk, which goes through all phases itself.

- `FilePath(path, context)` — splits a path into `path`, `name`, `parent`, `relPath`
  (relative to `context`) and checks that the file exists.
- `File(id, path, path_context, createFile=False)` — raises `FileNotFoundError` if the file
  does not exist. Reads the size and creates a default `Checksum` (SHA256) and `Encryption`.
- Phases: `Validate()`, `Encrypt(target="")`, `Write(tapeDrive)`, `Read(tapeDrive, target)`,
  `Decrypt(target)`. Each builds one `Command`, hands it to `Job` and returns the entry id;
  pass it as `dependsOn` to the next phase. All take `runlist` and `dependsOn`. A phase with
  nothing to do (checksum NONE, encryption NONE) returns `dependsOn`.
- `Validate()` creates the checksum if there is none yet, else it compares to the stored one.
  The same call is the check after a restore.
- `state` (`FileState`) is derived from the Job entries: `IDLE`, `QUEUED`, `CKSUM_CALC`,
  `VALIDATING`, `ENCRYPT`, `WRITE`, `READ`, `DECRYPT`, and the final `MISMATCH`, `ERROR`
  (`REMOVED` after `remove()`). Reading `state`, `cksum` or `encryption_scheme` takes over
  the results of finished phases, so nothing is stale.
- `path` stays the original file; `cryptPath` is the encrypted copy, `where` the plain file
  `Validate()` looks at (the original, or the restored one).
- File system: `touch()`, `remove()`, `append(text)`, `readSize()`. They are instant and need
  no Job.

Notes:
- A second `Validate()` / `Encrypt()` / `Decrypt()` while the first one is still pending, and
  any phase on a file in `ERROR` / `MISMATCH` / `REMOVED`, raises `RuntimeError`.
- `Read()` reads at the current tape position. Positioning by tape file number comes with
  the TapeDrive.
- A `File` can only be built for a file that exists. Restoring from a TOC on another machine
  needs a way to build one from the TOC entry (not done).
- Every `File` generates its own `Key`, which costs two `openssl` calls; `Folder` keeps it.

### Folder.py

All files below one directory, sub directories included, sharing one checksum type and
one encryption mode. Every file has its own key and IV. The files are sorted by relative
path (the tape order) and `File.id` counts from 1: it is the tape file number, tape file 0
is the TOC.

- `Folder(path, checksumType=SHA256, encryptionMode=E_Mode.NONE)`. Both are decided with the
  request and read-only afterwards (assigning raises `AttributeError`); build a new `Folder`.
- `queueChecksums(runlist="")` queues the checksum of every file and returns the entry ids.
- `queueWrite(tapeDrive, runlist="", spool=None, checksums=None)` queues, per file, the phases
  `Validate()` → `Encrypt()` → `Write()` (with `checksums` from `queueChecksums()` the first one is
  queued already) and returns the ids of the tape-write entries. Nothing is started here.
  With a runlist id, a failing file stops the files after it. With a spool, the encrypted
  files go there (`0001.crypt`), else next to the originals.

Notes:
- The checksum is taken from the plain file, before encryption.
- Without a spool the `.crypt` files are created next to the originals and not removed.

### Job.py

Global scheduler for `Command` objects. `Job` is used as a singleton: all methods are
static, the queue is shared process-wide. One queue for the whole host is what keeps the
thread limit.

- `Job.Add(cmd, tape="", dependsOn="", runlist="", always=False, prepare=None, waitFor=None, drive="")` → entry id.
  `drive` is the wwid of the drive whose request this is (a tape entry gets it from `tape`);
  `Job.Registry(drive=)` and `Job.Flush(drive=)` filter by it.
  An entry may depend on one parent and wait for more entries (`waitFor`, a list of ids, for example
  "all checksums are done"). All of them must be added first and `COMPLETED`; one `FAILED` fails the entry.
- `runlist` groups the entries of one request. If one of them fails, the entries of that
  runlist which have not started yet fail too; `always=True` marks closing steps that
  still run.
- `Job.Work(delayMs)` starts a background thread that calls `Job.Refresh()` periodically;
  `Job.Stop()` ends it. `Job.Refresh()` can also be called by hand (the tests do this).
- `prepare` is called right before the command starts, e.g. to write the file it reads (the
  last TOC). If it raises, the entry `FAILED` with the reason in `error`, the command never ran.
  `Job.Failed(runlist)` tells whether an entry of a runlist failed (closing steps do not count).
- `Job.Wait(ids, timeoutSec=0)` blocks until the entries are finished (drives `Refresh()`
  itself), `Job.Get(id)`, `Job.Registry()`, `Job.Flush(killRunning=True)`.
- Entry states: `WAITING_FOR_PARENT → READY4EXEC → RUNNING → COMPLETED | FAILED`.
  A failed parent fails all of its children.
- `Job.Add(cmd, urgent=True, deadlineMs=2000)` / `Job.Run(cmd, deadlineMs)` start a system command at once,
  outside the queue and the thread limit; a late one is killed (state `KILLED`). They live in `Job.urgent`.
- Scheduling: a tape device runs one entry at a time, strictly in the order of `Add()`.
  Everything else is limited by `Job.limit` (default: CPU count). Priority: tape entries,
  then entries that lead to a tape entry, then the rest.

Notes:
- Finished entries stay in the queue until `Flush()` is called (a new write or read request replaces the registry).
- [JOB.MD](JOB.MD) tells the whole story; this section is the short version.

### Tape.py

Describes the inserted tape, built from the 4-hex-digit id that the drive reports
(MODE SENSE): `Tape("3810")` = LTO-3, tape present, not write protected.

- Digit 1: LTO version, digit 2: `8` = tape present, digit 3: bit 3 set = write protected.
- Fields: `lto_version`, `native_capacity` (bytes), `native_rate` (ideal bytes/s), `write_protect`, `begin_of_tape`,
  `state` (`NO_TAPE`, `WRITE_PROTECT`, `ONLINE`), `blocksize`.
- Version `0` with tape present (`"0810"`) is a "custom" tape with capacity 0.

Notes:
- Capacities and rates are defined up to LTO-10; newer versions get 0.

### TapeDrive.py

One tape drive. It does four things, each one a step in the Job queue that returns the entry
id (pass it as `dependsOn`): `Rewind()` (SCSI REWIND), `Eject()` (SCSI LOAD/UNLOAD), `Write(source)`
(`dd` to the `nst` device, one tape file) and `Read(target)` (`dd` from the `nst` device, the
next tape file); `WriteRandom(size, blocksize)` writes test data for the block size benchmark. For reading it also seeks: `Space(files)` (SCSI SPACE over file marks, backward
if negative) and `SpaceEnd()` (to the end of the data). Everything is SCSI through `sg_raw` and
`dd`, there is no `mt`.
The long comment at the top of the file explains the SCSI commands and is worth reading.

- `TapeDrive(path, generic_path, drive_override=False, blocksize="256K", paths=None, wwid="")` —
  `path` is the non-rewinding device (`/dev/nst0`), `generic_path` the SCSI generic device
  (`/dev/sg0`). The constructor queries vendor/model/serial (INQUIRY) and the tape (MODE SENSE).
  `wwid` is the id the kernel gives the logical unit (read from sysfs if not given), `paths` all
  `(nst, sg)` pairs of a drive with several cables, `id` the key for the Job (`wwid`, else the path).
- All steps take `runlist`, `dependsOn`, `always` and `prepare` (see Job).
- `state` (`TD_State`) is derived from the Job entries: `IDLE`, `QUEUED`, the running step, or
  `ERROR` if the last finished step failed; the next good step clears it. `tape.begin_of_tape`
  follows the steps.
- Without SCSI tooling or hardware: `drive_override=True`, set `rewindCommand` / `ejectCommand`
  (their command line is the template for every step) and call `tapeOverride(Tape(...))`. `path`
  may then be a regular file.

Notes:
- **`Read()` must not use `dd iflag=fullblock`** and **nothing may read at the end of the data.**
  `fullblock` swallows the file mark after a short last block and reads on into the next tape
  file (first test: one `dd` returned the TOC and all 15 files in one piece). A read at the end
  of the data makes the kernel driver answer every later read with an I/O error, even after
  `Rewind()`, until the driver itself is repositioned (`mt rewind`, by the operator).
- Whether the drive can take a step is not asked before it yet (see DESIGN.md).
- A regular file as tape is truncated by every `Write()`.
- `Eject()` exists and is never part of a test run on the real drive.

### TableOfContent.py

The TOC is one JSON document: `{"header": {...}, "body": "<base64>"}`. The header is clear
text (format, version, fingerprint, state, host, blocksize, drive vendor/model/serial, tape,
body cipher); the body holds the folders with all files and their keys, encrypted with the
passphrase of the tape (`openssl aes-256-ctr -pbkdf2`).

- `TOC_Header(tapeDrive, threadCount, fingerprint="", bodyCipher=AES256CTR)` — a random
  fingerprint is created unless one is given. `header.state` is a `TOC_State`
  (`IDLE` / `COMPLETE` / `FAILED`).
- `TableOfContent(folder, header)` — `folder` is the one `Folder` of the request.
- `seal(passphrase)` → the JSON text to put on tape; `store(directory)` keeps a copy as
  `YYYYMMDD_hhmmss_<fingerprint>.json`.
- `removeEncryption()` — the unencrypted request: `body_cipher` and the mode of every file become
  NONE, the keys are dropped. Before the job is queued and before the first `seal()`. A plain TOC
  is sealed without passphrase (`seal()` refuses one) and its body is the JSON object, not base64.
- `TableOfContent.readHeader(text)` needs no passphrase; `TableOfContent.open(text,
  passphrase)` returns `{"header", "body"}` as dicts, `TOC_WrongPassphrase` if the body
  does not decrypt to JSON. A plain TOC needs no passphrase.

Notes:
- `_asdict()` is the whole TOC in clear text including keys. Tests and debugging only.
- Passphrase goes to `openssl` through the environment, the body through stdin; no plain
  text file is written.
- Not done yet: the trailing TOC on tape and reading a TOC from tape (see DESIGN.md).
- `TOC_Body` is gone.

### Spool.py

The spool directory of one job: `<mount>/rutbs-spool/<epoch>_<fingerprint>/`.

- `Spool(mountpoint, fingerprint)` — raises `ValueError` unless `mountpoint` is a mount
  point. `create()` makes the directory (mode 0700, `FileExistsError` if it exists),
  `file(id)` is the path `0001.crypt` of a tape file number, `remove()` deletes the
  directory (and `rutbs-spool` if it is empty). `remove()` refuses paths that are not below
  `rutbs-spool`.

### TD_Pool.py

Finds the tape drives. A drive with two SAS cables shows up as two `sg` / `nst` devices and
is ONE drive: devices are grouped by the `wwid` the kernel publishes in
`/sys/class/scsi_generic/sgN/device/wwid`, not by the serial number.

- `TD_Pool(sysfs=..., dev="/dev", drive_override=False)`.
- `scan()` reads sysfs only (no SCSI command) and returns one dict per drive: `wwid`,
  `vendor`, `model`, `paths` (`[(nst, sg), ...]`, sorted by sg number).
- `gatherDrives()` returns one `TapeDrive` per drive (it queries the drive) and keeps them
  in `drives`.
- A drive is never hidden: every tape with an `nst` device is listed. Paths that cannot be
  proven to be one drive (no `wwid`, or the same `wwid` with another vendor / model) are
  listed on their own, with a `[WARNING]` in `messages`. Only a tape without `nst` device
  is left out (`[ERROR]`).
- `TapeDrive.id` is the `wwid`, else the path: the Job key.

### Mount.py

One mounted file system from `findmnt`: `filesystem`, `fstype`, `size`, `used`, `avail`,
`mountpoint`. `Mount.list()` returns all, `Mount.of(path)` the one that holds an existing
path (`None` otherwise). Used by `Spool`; `Host` will use it for its status.

### Response.py

`flask.Response` with `_asdict()` / `__str__()`. Used by `Host`.

### Host.py — to be ported

Host status (CPU, memory, load, drives, mounts via `psutil`, `df`), the thread limit, and
the logic behind the REST API. Still written against the old `tbk` drive class; not
importable.

---

## Top level

### BlockSizeBenchmark.py

The block size benchmark of the tape format (rule and reasons in [TapeFormat.md](TapeFormat.md)). Same
shape as `WriteJob`: `queue()` (refuses no tape / write protected), `wait()`, `state`, `print(bench)`.
For each candidate it queues rewind + `TapeDrive.WriteRandom()`, at the end one more rewind, never an eject.
Destructive on purpose.

```python
bench = BlockSizeBenchmark(td)           # seconds=30 or size=bytes, candidates=None
bench.queue(); bench.wait()
bench.results                            # {block size in bytes: bytes/s} of the candidates that worked
bench.blocksize, bench.note              # "256K", and a hint if none was good enough
BlockSizeBenchmark.pick(results, ideal)  # the rule alone
```

- A candidate that fails is left out and stops nothing (every step is `always`, no `dependsOn`).
- Nothing is written to the cartridge memory yet.

### WriteJob.py

The complete run list of one write request, queued in one go:
`all checksums → rewind → first TOC → per file: encrypt, write → last TOC → rewind [→ eject]`.

```python
job = WriteJob(input_dir, td, "passphrase", "/stornvme")     # td from TD_Pool().gatherDrives()[0]
job.queue()      # checks the request, creates the spool, queues everything
job.wait()       # blocks; or poll job.state: NEW, RUNNING, COMPLETED, FAILED
print(job)       # state and the state of every file
```

- `WriteJob(inputDir, tapeDrive, passphrase, spoolMount, tocDir="", checksum=SHA256,
  encryption=AES256CBC, eject=False, unencrypted=False)`.
- No passphrase is refused ("Passphrase for encryption required") unless `unencrypted=True`; then
  the TOC removes all encryption and a passphrase is refused as well (they exclude each other).
  `encryption=NONE` without `unencrypted` is refused too.
- The drive idles until every checksum is known (a barrier entry waits for them, the rewind depends on
  it). The first TOC is sealed by a `prepare` hook right before it is written (state IDLE, all
  checksums inside). The last TOC is made the same way after the files, with the results; its state
  is COMPLETE, or FAILED if any step failed. Both are equivalent except for the state and the command log.
- If a checksum fails, the tape is not touched: no TOC is written (the last TOC checks that the first
  one is on the tape), only the closing rewind runs. After a later failure no further file is
  written, the last TOC and the rewind still run, the eject does not. A copy of the last TOC goes to `tocDir`.
- `queue()` refuses: no files, no tape, write protected tape, files larger than the native
  capacity, spool mount with less free space than the input.
- The spool directory is removed at the end.
- `eject=True` is the only way a WriteJob ejects.

### ReadJob.py

The restore of a whole tape. Two steps, because the operator is asked for the passphrase after
seeing which tape is loaded.

```python
job = ReadJob(td, "/data/restore", "/stornvme", tocDir="/data/tocs")
job.open()                    # rewind, first TOC, to the end, last TOC, rewind -> the clear text headers
job.queue("passphrase")       # TOC_WrongPassphrase: nothing was queued, ask again
job.wait()                    # then job.state: COMPLETED only if every file is IDLE (checksum ok)
```

- `open()` reaches the last TOC with SPACE to the end, two file marks back, one forward. It
  never reads at the end of the data. A tape without a last TOC is not complete; the copy in
  `tocDir` (named by the fingerprint) is used instead, with a warning in `messages`.
- `queue()` opens both TOCs, compares them (`TableOfContent.differences()`: same tape, same files,
  same keys; checksums and states are results and may differ) and queues
  `skip first TOC → per file: Read → Decrypt → Validate → rewind`. The checksums come from the last TOC (the same as in the first).
- Refused: the TOCs disagree, the writing job had failed, a file exists already in the target,
  target or spool mount too small. `File.Restore()` keeps every file inside the target directory.
- With `tocDir` both TOCs are also kept there in clear text, `*.first.plain.json` and
  `*.last.plain.json`, mode 0600. They contain the keys of every file: delete them when done.
- Not restored: modification time and permissions (the TOC does not record them yet).

### write_folder_to_tape.py

Command line wrapper around one `WriteJob`, from a sprint. It goes away once the REST API can do
the same. The passphrase comes from `RUTBS_PASSPHRASE` or is asked for.

```
RUTBS_PASSPHRASE=... python3 write_folder_to_tape.py --dir /data/in --spool /stornvme
RUTBS_PASSPHRASE=... python3 write_folder_to_tape.py --dir /data/in --spool /mnt/data \
        --tape /tmp/faketape.bin --rewind-cmd true --eject-cmd true
```

Options: `--checksum`, `--encryption`, `--threads` (default 4), `--toc-dir`, `--eject` (off by
default), and for a regular file as tape `--tape`, `--rewind-cmd`, `--eject-cmd`, `--lto-version`.

### benchmark_tape.py

Command line wrapper around one `BlockSizeBenchmark`; prints the table and the pick. **Overwrites the
tape from its begin**, never ejects. `--seconds`, `--size`, `--blocksizes 256,384`, and for a regular
file as tape `--tape`, `--rewind-cmd`, `--lto-version`.

### read_tape_to_folder.py

Command line wrapper around one `ReadJob`, goes away together with `write_folder_to_tape.py`. Shows
the tape (fingerprint, date, host, state of both TOCs), then asks for the passphrase (three
tries) or takes `RUTBS_PASSPHRASE`. The tape is rewound, never ejected.

```
python3 read_tape_to_folder.py --target /data/restore --spool /stornvme --toc-dir /data/tocs
```

### rbs_backend.py — to be ported

Flask REST API (port 5533, Swagger via flasgger) with `/host/...` and `/drive/<alias>/...`
endpoints. Depends on `Host` and `tbk`; not importable. `docs/sequenceDiagrams.md`
describes this API.

---

## Tests

Plain `unittest`, one file per class. Run one with `python3 UT_<name>.py`, all with
`./UnitTest.sh`.

| File | Covers | Needs |
|------|--------|-------|
| `UT_Version.py` | 16 bit version value | — |
| `UT_Command.py` | start, wait, timeout, kill, stdout/stderr, hex output, `/proc` io, env, quoting | `ping`, `dd`, fixtures `cmd/` |
| `UT_File.py` | create, touch, remove, append; the phases against a fake tape: derived state, pass-through, tape and back, damaged tape, refusals | fixtures `file/`, `openssl` |
| `UT_Checksum.py` | `File.Validate()`: create and compare, MD5 / SHA256 / SHA512, mismatch | fixtures `cksum/` |
| `UT_Encryption.py` | key generation, Validate → Encrypt → Decrypt → Validate for all modes, wrong key | fixtures `encryption/` |
| `UT_Tape.py` | hardware id parsing | — |
| `UT_TD_Pool.py` | fake sysfs: two paths of one drive, natural sg order, nothing hidden | — |
| `UT_Spool.py` | `/mnt/daten` is found as mount, spool create / remove, refusals | `findmnt`, `/mnt/daten` as mount |
| `UT_Job.py` | dependencies, failure propagation, priorities, tape order, runlist abort, `waitFor`, scheduler thread, `prepare`, `Failed()` | — |
| `UT_TapeDrive.py` | the commands of the steps (incl. seeking), derived state, override template, error cleared by the next good step | — |
| `UT_BlockSizeBenchmark.py` | the pick rule (incl. the default and the note), the run list on a fake drive, a failing candidate stops nothing | `openssl`, `dd` |
| `UT_ReadJob.py` | key and file restored from the TOC, checksum mismatch, comparison of the two TOCs, no escape from the target; **on the real drive** (`RUTBS_TEST_TAPE=1`, overwrites the tape from its begin): write, read back, wrong passphrase | `openssl`, `/mnt/daten` (or `RUTBS_TEST_MOUNT`) |
| `UT_WriteJob.py` | the whole run list on a fake drive: order, last TOC, eject only on request, a failing file, refused requests, both TOCs equivalent, an unreadable file leaves the tape alone | `openssl`, `/mnt/daten` as mount |
| `UT_Folder.py` | file collection, recursion and order, odd file names, own key per file, write chain against a fake tape, spool, abort | `openssl`, `/mnt/daten` as mount |
| `UT_TableOfContent.py` | header, seal / open round trip, wrong passphrase, TOC directory | `openssl` |

- Fixtures live in `/mnt/daten/testfiles/rutbs4` (absolute path, outside the repository).
- `UT_File` creates and deletes files in its fixture folder while running; `UT_Encryption` leaves the fixture as it was (it writes `.crypt` / `.restored` next to it and removes them).
- `UnitTest.sh` runs everything but always exits 0; read the output.
- Verified on 2026-11-18: all fourteen test files pass; `UT_ReadJob` also on the real LTO-8.

---

## Known issues

Reproduced on 2026-11-16 unless marked "(read)". Most of them are settled by the target
design and disappear with the steps listed in [DESIGN.md](DESIGN.md).

1. **Restore:** modification time and permissions are not restored (not in the TOC), a single
   file cannot be restored on its own yet (the seeking exists), the spool is not emptied while
   the restore runs.
2. With a regular file as fake tape, each `dd` truncates the file: only the last file
   written remains (the last TOC). Tests without hardware can therefore not read back several files.
3. **The spool needs as much free space as the whole input.** Nothing holds back the
   encryption while the tape is slower, and a spool file is not deleted after the drive has
   taken it (only the clean-up at the end does). `WriteJob` refuses a request whose input is
   larger than the free space of the spool mount.
4. The drive is not asked whether it can take a step; `TapeDrive` only knows its own Job entries.
5. `Host` and `rbs_backend.py` cannot be imported.
6. `docs/classDiagram.md`, `docs/sequenceDiagrams.md`, `docs/JOB.MD` and `docs/todo.md`
   describe older designs and no longer match the code.

Changed on 2026-11-19: the first and the last TOC are equivalent. The drive idles until every
checksum is known, then the first TOC (with the checksums) is written; before, the checksums were
only in the last TOC. `Job` got `waitFor`. A failed checksum leaves the tape untouched.

Fixed on 2026-11-18 (second part): restoring works, checked on the real LTO-8 (`diff -r` identical).
The old test tape had no last TOC at all (the first test called `writeTOC` a second time and it
returned silently because the tape was not at its begin; that method is gone). It could be restored
with the copy from the TOC directory.

Fixed on 2026-11-18: the job did not do everything (rewind, first and last TOC, rewind and
an optional eject were typed by hand) - `WriteJob` queues the whole run list; `TapeDrive` has only
the four steps; every `__str__` is `indent=2`; the checksum defaults to SHA256; `Folder` settings
are read-only after construction.

Fixed on 2026-11-17: the keys are no longer in plain text on the tape (encrypted TOC body);
there is one way to run a phase (the Job), `File.state` no longer lags behind, and
`Checksum.setType()` after construction works; `TD_Pool` finds drives and treats the
two paths of a dual-cabled drive as one.

Fixed on 2026-11-16: files were written to tape in completion order instead of queue
order; `File.encrypt()` could delete the original before the encryption had started; file
names with spaces or `'` were rejected or broke commands; the key was visible on the
`openssl` command line; `TapeDrive.write()` put the drive into `ERROR`; `Tape` raised
`KeyError` for LTO-11 and newer.

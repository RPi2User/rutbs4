# Source Overview

One short section per source file: what it does, how to use it, what to watch out for.
State: working tree of 2026-11-16. Where the project is heading: [DESIGN.md](DESIGN.md).

## Big picture

rutbs4 writes files to LTO tape. Everything is done by shelling out to standard tools
(`dd`, `openssl`, `sg_raw`, `find`, `stat`); Python only builds the command strings and
tracks their state.

```
write_folder_to_tape.py          <- the only working entry point
  ├─ TapeDrive ── Tape           drive + inserted tape
  ├─ Folder ── File              what to write
  │             ├─ Checksum
  │             └─ Encryption ── Key
  ├─ Spool ── Mount              where the encrypted files wait
  ├─ TableOfContent              JSON description, first file on tape
  └─ Job                         runs the queued Commands
All of the above use Command (subprocess wrapper).
```

There are two generations of code in the repository:

| Status | Files |
|--------|-------|
| **Current**, importable, unit tests pass | `Version`, `Command`, `Checksum`, `Encryption`, `File`, `Folder`, `Spool`, `Mount`, `Job`, `Tape`, `TapeDrive`, `TD_Pool`, `TableOfContent`, `write_folder_to_tape.py` |
| **To be ported**, not importable | `Host`, `rbs_backend.py` — the REST layer. Still written against the package `tbk`, which no longer exists (renamed to `_old_tbk/`, git-ignored). `Response` belongs to it. |

Conventions used by all current classes:

- `_asdict()` returns a JSON-ready dict, `__str__()` returns it as a JSON string.
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

- `Command(cmd, filesize=-1, raw=False, env=None)` — does not start anything.
- `env` adds environment variables. Use it for secrets: they do not appear in `ps` or in
  `_asdict()`.
- `Command.quote(path)` wraps a path in single quotes; use it for every path in a command.
- `start()` runs it in the background, `wait(timeout=0)` blocks (starts it if needed;
  timeout in units of 10 ms, 0 = wait forever), `kill()` sends SIGTERM,
  `reset()` makes the object reusable, `status()` refreshes all fields.
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
  known value, `wait()` runs it and stores the result in `value`. Each builds a new
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
  (blocking, two subprocesses). Both are hex strings in `value` / `iv`.
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

- `Folder(path, checksumType, encryptionMode=E_Mode.NONE)`.
- `queueWrite(tapeDrive, runlist="", spool=None)` queues, per file, the phases `Validate()` →
  `Encrypt()` → `Write()` and returns the ids of the tape-write entries. Nothing is started here.
  With a runlist id, a failing file stops the files after it. With a spool, the encrypted
  files go there (`0001.crypt`), else next to the originals.

Notes:
- The checksum is taken from the plain file, before encryption.
- Without a spool the `.crypt` files are created next to the originals and not removed.

### Job.py

Global scheduler for `Command` objects. `Job` is used as a singleton: all methods are
static, the queue is shared process-wide. One queue for the whole host is what keeps the
thread limit.

- `Job.Add(cmd, tape="", dependsOn="", runlist="", always=False)` → entry id. An entry may
  depend on one parent, which must be added first.
- `runlist` groups the entries of one request. If one of them fails, the entries of that
  runlist which have not started yet fail too; `always=True` marks closing steps that
  still run.
- `Job.Work(delayMs)` starts a background thread that calls `Job.Refresh()` periodically;
  `Job.Stop()` ends it. `Job.Refresh()` can also be called by hand (the tests do this).
- `Job.Wait(ids, timeoutSec=0)` blocks until the entries are finished (drives `Refresh()`
  itself), `Job.Get(id)`, `Job.Registry()`, `Job.Flush(killRunning=True)`.
- Entry states: `WAITING_FOR_PARENT → READY4EXEC → RUNNING → COMPLETED | FAILED`.
  A failed parent fails all of its children.
- Scheduling: a tape device runs one entry at a time, strictly in the order of `Add()`.
  Everything else is limited by `Job.limit` (default: CPU count). Priority: tape entries,
  then entries that lead to a tape entry, then the rest.

Notes:
- Finished entries stay in the queue until `Flush()` is called.
- The class docstring is accurate and more detailed than this section.

### Tape.py

Describes the inserted tape, built from the 4-hex-digit id that the drive reports
(MODE SENSE): `Tape("3810")` = LTO-3, tape present, not write protected.

- Digit 1: LTO version, digit 2: `8` = tape present, digit 3: bit 3 set = write protected.
- Fields: `lto_version`, `native_capacity` (bytes), `write_protect`, `begin_of_tape`,
  `state` (`NO_TAPE`, `WRITE_PROTECT`, `ONLINE`), `blocksize`.
- Version `0` with tape present (`"0810"`) is a "custom" tape with capacity 0.

Notes:
- Capacities are defined up to LTO-10; newer versions get capacity 0.

### TapeDrive.py

One tape drive. Talks SCSI through `sg_raw` and moves data with `dd`.
The long comment at the top of the file explains the SCSI commands and is worth reading.

- `TapeDrive(path, generic_path, drive_override=False, blocksize="256K", paths=None, wwid="")` —
  `path` is the non-rewinding device (`/dev/nst0`), `generic_path` the SCSI generic device
  (`/dev/sg0`). The constructor queries vendor/model/serial and the tape. `wwid` is the id
  the kernel gives the logical unit (read from sysfs if not given), `paths` all
  `(nst, sg)` pairs of a drive with several cables, `id` the key for the Job (`wwid`, else the path).
- `rewind()`, `eject()`, `write(file)`, `read(file)`, `writeTOC(toc)`, `clearError()`.
- States (`TD_State`): `IDLE`, `READ`, `WRITE`, `REWIND`, `EJECT`, `WRITE_TOC`, `ERROR`, …
  Operations are silently ignored unless the drive is `IDLE`.
- Without SCSI tooling or hardware: `drive_override=True`, then set `rewindCommand` /
  `ejectCommand` and call `tapeOverride(Tape(...))`. `path` may then be a regular file.

Notes:
- `write()` and `read()` are the old single-file way. `File.Write()` / `File.Read()` replace
  them, they go when the positioning is done. `rewind()` and `eject()` start their
  commands on their own.
- `writeTOC(sealedToc)` takes the text from `TableOfContent.seal()`, blocks until it is on
  tape, and only works at begin of tape.
- `format()` is a stub that always raises.
- Every `_asdict()` on a real drive runs two `sg_raw` calls.

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
- `TableOfContent.readHeader(text)` needs no passphrase; `TableOfContent.open(text,
  passphrase)` returns `{"header", "body"}` as dicts, `TOC_WrongPassphrase` if the body
  does not decrypt to JSON.

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

### write_folder_to_tape.py

Command line tool from a sprint, currently the only working entry point (not yet
committed). It goes away once the REST API can do the same.

Steps: create drive → scan folder → rewind → ask for the passphrase (`RUTBS_PASSPHRASE` or prompt) → write sealed TOC → queue all files → run `Job` →
print one result line per file. Exit code 0 only if every file was written.

```
python3 write_folder_to_tape.py --dir /data/out --tape /dev/nst0 --generic /dev/sg0
python3 write_folder_to_tape.py --dir /data/out --tape /tmp/faketape.bin \
        --drive-override --rewind-cmd "true"
```

Options: `--checksum` (md5, sha256, sha512, none), `--encryption` (none, aes128cbc,
aes256cbc, aes128ctr, aes256ctr), `--blocksize`, `--lto-version`.
The key and IV of every file are printed to the terminal.

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
| `UT_Job.py` | dependencies, failure propagation, priorities, tape order, runlist abort, scheduler thread | — |
| `UT_Folder.py` | file collection, recursion and order, odd file names, own key per file, write chain against a fake tape, spool, abort | `openssl`, `/mnt/daten` as mount |
| `UT_TableOfContent.py` | header, seal / open round trip, wrong passphrase, TOC directory | `openssl` |

- Fixtures live in `/mnt/daten/testfiles/rutbs4` (absolute path, outside the repository).
- `UT_File` creates and deletes files in its fixture folder while running; `UT_Encryption` leaves the fixture as it was (it writes `.crypt` / `.restored` next to it and removes them).
- `UnitTest.sh` runs everything but always exits 0; read the output.
- Verified on 2026-11-17: all eleven test files pass.

---

## Known issues

Reproduced on 2026-11-16 unless marked "(read)". Most of them are settled by the target
design and disappear with the steps listed in [DESIGN.md](DESIGN.md).

1. **There is no trailing TOC yet.** `write_folder_to_tape.py` writes the first TOC only.
2. **Nothing can be restored yet.** A sealed TOC can be opened from text, but there is no
   read from tape.
3. With a regular file as fake tape, each `dd` truncates the file: only the last file
   written remains, the TOC is overwritten. Tests without hardware can therefore only
   cover a single file.
4. **The spool needs as much free space as the whole input.** Nothing holds back the
   encryption while the tape is slower, and a spool file is not deleted after the drive has
   taken it (only `Spool.remove()` at the end does). Plan the spool mount for the full
   encrypted size of the input directory.
5. `write_folder_to_tape.py` does not use the spool yet, so its `.crypt` files are written next to the originals and never removed.
6. `Host` and `rbs_backend.py` cannot be imported.
7. `docs/classDiagram.md`, `docs/sequenceDiagrams.md`, `docs/JOB.MD` and `docs/todo.md`
   describe older designs and no longer match the code.

Fixed on 2026-11-17: the keys are no longer in plain text on the tape (encrypted TOC body);
there is one way to run a phase (the Job), `File.state` no longer lags behind, and
`Checksum.setType()` after construction works; `TD_Pool` finds drives and treats the
two paths of a dual-cabled drive as one.

Fixed on 2026-11-16: files were written to tape in completion order instead of queue
order; `File.encrypt()` could delete the original before the encryption had started; file
names with spaces or `'` were rejected or broke commands; the key was visible on the
`openssl` command line; `TapeDrive.write()` put the drive into `ERROR`; `Tape` raised
`KeyError` for LTO-11 and newer.

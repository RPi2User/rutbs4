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
  ├─ TableOfContent              JSON description, first file on tape
  └─ Job                         runs the queued Commands
All of the above use Command (subprocess wrapper).
```

There are two generations of code in the repository:

| Status | Files |
|--------|-------|
| **Current**, importable, unit tests pass | `Version`, `Command`, `Checksum`, `Encryption`, `File`, `Folder`, `Job`, `Tape`, `TapeDrive`, `TableOfContent`, `write_folder_to_tape.py` |
| **To be ported**, not importable | `Host`, `rbs_backend.py` — the REST layer. Still written against the package `tbk`, which no longer exists (renamed to `_old_tbk/`, git-ignored). `Mount` and `Response` belong to it. |
| Unfinished | `TD_Pool` (imports, but does not find drives) |

Conventions used by all current classes:

- `_asdict()` returns a JSON-ready dict, `__str__()` returns it as a JSON string.
- Objects are small state machines. Calling `_asdict()` / `refresh()` / `_status()` first
  polls the underlying `Command` and then advances the state.
- Creating an operation (`Checksum.create()`, `Encryption.encrypt()`, `TapeDrive.write()`)
  only **builds** the `Command`. Something else has to start it: `Job`, or a `wait()` call.

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
  known value, `wait()` runs it and stores the result in `value`.
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
- `Encryption(key, mode=E_Mode.AES256CBC, keepOrig=True)`.
- `encrypt(path)` prepares `path` → `path + ".crypt"`; `decrypt(path)` prepares the reverse
  (strips the last extension). The result path is in `targetPath`, the command in `cmd`.
- `E_Mode.NONE` turns both into no-ops. States (`E_State`): `IDLE`, `ENCRYPT`, `DECRYPT`, `ERROR`.

Notes:
- The key is used as a passphrase (`-pass env:RUTBS_KEY`), not as raw key. openssl derives
  the real AES key from it, so `KeyLength` does not have to match the AES mode.
- The key is not on the command line, but `Key._asdict()` still prints key and IV.

### File.py

One file on disk, with its checksum and encryption.

- `FilePath(path, context)` — splits a path into `path`, `name`, `parent`, `relPath`
  (relative to `context`) and checks that the file exists.
- `File(id, path, path_context, createFile=False)` — raises `FileNotFoundError` if the file
  does not exist. Reads the size and creates a default `Checksum` (SHA256) and `Encryption`.
- File system: `touch()`, `remove()`, `append(text)`, `readSize()`.
- Operations: `createChecksum()`, `validateIntegrity(target)`, `encrypt()`, `decrypt()`,
  then `wait()` to run them. `refresh()` advances the state.
- States (`FileState`): `IDLE` is the only state that accepts new operations;
  `MISMATCH`, `REMOVED`, `ERROR` are final.

Notes:
- The class docstring is out of date (`path_context` is missing, `destroy()` does not exist).
- Every `File` generates its own `Key`, which costs two `openssl` calls; `Folder` replaces
  it right away.
- `encrypt()` / `decrypt()` followed by `wait()` is a second way to run a phase, next to
  `Folder.queueWrite()` + `Job`. The target design keeps only the `Job` way.

### Folder.py

All files directly inside one directory (not recursive), sharing one checksum type and
one encryption mode. Every file has its own key and IV.

- `Folder(path, checksumType, encryptionMode=E_Mode.NONE)`.
- `queueWrite(tapeDrive, runlist="")` adds, per file, the chain *checksum → encrypt → `dd`
  to tape* to `Job` and returns the ids of the tape-write entries. Nothing is started here.
  With a runlist id, a failing file stops the files after it.
- `finalizeChecksums()` — call after the entries have finished, copies the results into
  `file.cksum.value`.
- `encrypt()` / `decrypt()` are empty stubs.

Notes:
- The checksum is taken from the plain file, before encryption.
- The `.crypt` files are created next to the originals and are not removed afterwards.

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
- `Job.Get(id)`, `Job.Registry()`, `Job.Flush(killRunning=True)`.
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

- `TapeDrive(path, generic_path, drive_override=False, blocksize="256K")` —
  `path` is the non-rewinding device (`/dev/nst0`), `generic_path` the SCSI generic device
  (`/dev/sg0`). The constructor queries vendor/model/serial and the tape.
- `rewind()`, `eject()`, `write(file)`, `read(file)`, `writeTOC(toc)`, `clearError()`.
- States (`TD_State`): `IDLE`, `READ`, `WRITE`, `REWIND`, `EJECT`, `WRITE_TOC`, `ERROR`, …
  Operations are silently ignored unless the drive is `IDLE`.
- Without SCSI tooling or hardware: `drive_override=True`, then set `rewindCommand` /
  `ejectCommand` and call `tapeOverride(Tape(...))`. `path` may then be a regular file.

Notes:
- `write()` builds its command but does not start it; hand `command` to `Job`.
  `rewind()`, `eject()` and `read()` still start theirs on their own.
- `writeTOC()` blocks until the TOC is on tape, and only works at begin of tape.
- `format()` is a stub that always raises.
- Every `_asdict()` on a real drive runs two `sg_raw` calls.

### TableOfContent.py

JSON description of what is on the tape. It is written as the first file on tape.

- `TOC_Header(tapeDrive, threadCount)` — timestamp, hostname and a snapshot of the drive.
- `TableOfContent(rootFolder, header)` — also scans the direct subdirectories of the root
  folder (one level) into `folder`.
- `TOC_Body` is an unused stub.

Notes:
- There is no way yet to parse a TOC back from JSON, so nothing can be read from tape
  with it.

### TD_Pool.py

Meant to find all tape drives: `/dev/sg*` devices of group `tape`, mapped to their
`/dev/nstX` device through sysfs. Not used anywhere and not functional yet (see known
issues).

### Mount.py

Plain data holder for one mounted file system. Used by `Host`.

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

Steps: create drive → scan folder → rewind → write TOC → queue all files → run `Job` →
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
| `UT_File.py` | create, touch, remove, append | fixtures `file/` |
| `UT_Checksum.py` | create and validate, MD5 / SHA256 / SHA512, mismatch | fixtures `cksum/` |
| `UT_Encryption.py` | key generation, encrypt → decrypt round trip for all modes | fixtures `encryption/` |
| `UT_Tape.py` | hardware id parsing | — |
| `UT_Job.py` | dependencies, failure propagation, priorities, tape order, runlist abort, scheduler thread | — |
| `UT_Folder.py` | file collection, odd file names, own key per file, write chain against a fake tape, abort | `openssl` |

- Fixtures live in `/mnt/daten/testfiles/rutbs4` (absolute path, outside the repository).
- `UT_File`, `UT_Checksum` and `UT_Encryption` modify the fixture files while running.
- `UnitTest.sh` runs everything but always exits 0; read the output.
- Verified on 2026-11-16: all eight test files pass.

---

## Known issues

Reproduced on 2026-11-16 unless marked "(read)". Most of them are settled by the target
design and disappear with the steps listed in [DESIGN.md](DESIGN.md).

1. **Key is stored in plain text on the tape.** `TableOfContent._asdict()` includes every
   file's `Encryption`, and with it the key and IV. Solved by the encrypted TOC body.
2. **The TOC is incomplete.** It lists the files of subfolders, but
   `write_folder_to_tape.py` only writes the root folder; only one directory level is
   scanned. There is no trailing TOC yet.
3. **The TOC cannot be read back.** There is no parser, so nothing can be restored.
4. With a regular file as fake tape, each `dd` truncates the file: only the last file
   written remains, the TOC is overwritten. Tests without hardware can therefore only
   cover a single file.
5. `.crypt` files are written next to the originals and never removed (no spool yet).
6. `TD_Pool.gatherDrives()` reads the exit code right after `start()`, while the command is
   still running, and therefore reports "No Drives Found".
7. `Host` and `rbs_backend.py` cannot be imported.
8. `docs/classDiagram.md`, `docs/sequenceDiagrams.md`, `docs/JOB.MD` and `docs/todo.md`
   describe older designs and no longer match the code.

Fixed on 2026-11-16: files were written to tape in completion order instead of queue
order; `File.encrypt()` could delete the original before the encryption had started; file
names with spaces or `'` were rejected or broke commands; the key was visible on the
`openssl` command line; `TapeDrive.write()` put the drive into `ERROR`; `Tape` raised
`KeyError` for LTO-11 and newer.

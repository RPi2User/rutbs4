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
(`backend/Version.py`): 4 bit major, 4 bit minor, 8 bit bugfix. `4.0.0` = `0x4000`.

## Tape layout

```
tape file 0      TOC, state WRITING     the plan: order, sizes, keys
tape file 1..N   the files, in exactly the order of the TOC
tape file N+1    TOC, state COMPLETE    the result: same content plus checksums
```

- The **tape file number** is the position of a file. It is stored in the TOC, and
  `mt fsf <n>` jumps to it.
- The order is fixed when the job is created (sorted by relative path). Nothing about it
  depends on timing, so the first TOC can be written before any file is processed.
- The second TOC gives redundancy (a damaged begin of tape does not lose the tape) and is
  the final write test: if it is on the tape, everything before it fits.
- **Tape cannot be changed in place.** Writing at the begin of tape makes everything
  behind it unreadable. The first TOC therefore always says `WRITING`. A tape is good only
  if a trailing TOC with state `COMPLETE` exists. On a failed job the trailing TOC is
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

## Table of content (proposal)

One JSON document per TOC. The header is clear text, the body is encrypted with the
passphrase of the tape and stored as base64:

```json
{
  "header": {
    "format": "rutbs",
    "version": 16384,
    "fingerprint": "8f1c…",
    "state": "WRITING | COMPLETE | FAILED",
    "created": "2026-11-16T10:00:00",
    "hostname": "tape-01",
    "blocksize": "256K",
    "drive": { "vendor": "IBM", "model": "ULT3580-HH8", "serial": "10WT083661" },
    "tape": { "lto-version": "LTO_8", "native_capacity": 12000000000000 },
    "body_cipher": "AES256CTR"
  },
  "body": "<base64 of the encrypted JSON below>"
}
```

```json
{
  "files": [
    {
      "id": 1,
      "relPath": "photos/2024/a.img",
      "size": 4294967296,
      "mtime": 1731751200,
      "mode": "0644",
      "cksum": { "type": "SHA256", "value": "…" },
      "encryption": { "mode": "AES256CTR", "key": "…", "iv": "…" }
    }
  ]
}
```

- `id` is the tape file number.
- The checksum is taken from the plain file. It sits in the encrypted body, so it reveals
  nothing. In the first TOC the values are still empty.
- Key hierarchy: passphrase (from the API request) → TOC body → key of each file.
  A wrong passphrase shows as a body that is not valid JSON.
- Only these fields go to tape. Runtime details of the objects (commands, pids, states)
  do not belong in a TOC.
- A copy of every final TOC is kept on the host in a catalog directory, named after the
  fingerprint. That is the "database": it answers which tape holds a file, and a
  passphrase can be tested against it without loading the tape.

## Job

A **Job** is the complete run list of one request, for example a write:

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

Today `backend/Job.py` is one global queue. **(proposal)** It becomes: one scheduler
(global, owns the thread limit) and `Job` objects (one per request, own the run list).

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

**(proposal)** Each phase only prepares one `Command` and hands it to the job. The file
derives its state from those commands. There is no second, blocking way to run a phase.

- The relative path of a file is kept, so a directory tree is restored 1:1.
  Sub directories are scanned recursively.
- Restored metadata: modification time and permissions.
- Restoring a single file: read the TOC, jump to the tape file number, read that one
  file, rewind and eject, report success or not-found.

## Spool and paths

- The host knows its mounts so that input, output and spool can be placed deliberately.
- Input and output path arrive with the API request. A request is answered with an error
  until it is complete; nothing is guessed.
- Every job gets its own spool directory:
  `<mount>/rutbs-spool/<epoch>_<fingerprint>/` with the TOC, the checksum list and the
  encrypted files. It is removed when the job is done.
- **(proposal)** Encrypted files in the spool are named after their tape file number
  (`0001.crypt`), because two files in different directories may share a name.

## Security

- Passphrase per tape, supplied by the operator with the request, never stored.
- Secrets are passed to `openssl` through the environment, not the command line, and are
  not part of any status output.
- All cipher modes stay available so new ones can be added and old tapes stay readable.

## Drives

- The backend finds the drives itself and reports vendor, model, serial, device paths and
  state. One implementation, run at start and on request.
- A drive is identified by its **serial number**. The same drive reachable on several
  paths (SAS multipath: `/dev/nst0` and `/dev/nst1`) is one drive. A drive without a
  readable serial is rejected: `TapeDrive Serial not readable`.
- Position: the backend only knows "at begin of tape" or "not". It rewinds itself before
  it starts a job.
- Block size belongs to the tape and is stored in the TOC header. Default `256K`.
  A benchmark that helps the operator choose is planned.

## Host and REST API

- The host has a stable fingerprint, so a frontend can recognise it and send the matching
  configuration. **(proposal)** Derived from `/etc/machine-id`; no file of our own needed.
- Configuration (paths, thread limit, …) is set at run time through the API and held in
  memory. The frontend is responsible for providing it.
- Long operations do not block the request: `POST` returns a job id, the progress is polled.
- One status request returns everything a frontend needs for its graphs (CPU, memory,
  load, mounts, drives, jobs), each response with a timestamp. Parts can be requested
  separately.
- GUI and CLI clients live outside this repository.

## Open points

1. Version word: the notes said `0b1000 …` for major 4. Implemented is the plain binary
   value, `0b0100 …` = `0x4000`.
2. TOC as JSON (current code) or XML (the spool example mentioned `toc.xml`).
3. One key per tape or one per file. The TOC layout above allows both.
4. Catalog as a directory of TOC files, or a real database.
5. Whether the manufacturer's medium serial number (chip attribute `0x0401`, read-only)
   should be used as fingerprint when the chip is readable. It would never need writing.

## Next steps

1. Job: scheduler + `Job` objects with a run list and abort handling.
2. File: phase methods on top of the job; remove the blocking path and the duplicate
   state machines.
3. TOC: the layout above, encrypted body, parsing; spool handling.
4. TapeDrive: positioning by tape file number, drive discovery by serial. Needs hardware.
5. Host and REST API on the new core; then remove `write_folder_to_tape.py`.
6. Cartridge memory. Needs hardware.

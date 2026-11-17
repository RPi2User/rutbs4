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

- The **tape file number** is the position of a file. It is stored in the TOC, and
  `mt fsf <n>` jumps to it.
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
- If the backend is started with a TOC directory, every final TOC is also stored there as
  `YYYYMMDD_hhmmss_<fingerprint>.json`. This loose collection answers which tape holds a
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
  It is the master key: it encrypts the TOC body, and with it the keys of all files.
- Every file is encrypted with its own random key and IV.
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
  configuration. It is taken from `/etc/machine-id`; alternatively the backend is started
  with an id of choice as command line argument.
- Command line arguments of the backend: port, TOC directory, host id. Everything else is
  configured at run time.
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
body, reading from text and TOC directory.

1. TOC: reading it back from tape (needs the drive, see 3), files of sub directories.
2. File: phase methods on top of the queue; remove the blocking path and the duplicate
   state machines. Recursive scan, spool directory.
3. TapeDrive: positioning by tape file number, trailing TOC, drive discovery by serial.
   Needs hardware.
4. Host and REST API on the new core; then remove `write_folder_to_tape.py`.
5. Cartridge memory. Needs hardware.

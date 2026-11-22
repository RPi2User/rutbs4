# RUTBS-UI

- UI:           gtk4, tabs mit den Servern, XML-Viewer
- Backend:      network-daemon, checksumming, parallel
- Transport:    JSON-like API-Calls, Port 5533
- CLI:          

path, optimal-blocksize, ltoV (es könnten mehr als 1 drive/pc angeschlossen sein!)

- Drive state machine: ask the drive for its state before every action except trivial ones (CM read, status). Find the SCSI query that shows "busy" while a write runs. See DESIGN.md, "Drives".
- **RC:** Tape format with the bandwidth measurement / block size benchmark (destructive on purpose), result into the cartridge memory. See [TapeFormat.md](TapeFormat.md).
- **Invalidate the tape if there is no space left.** If the write fails with "No space left on device", the tape gets a
  new TOC at its begin: state `FAILED` and an **empty body**, the files are removed from it. Nobody must get the idea that
  files 1..n-1 were written successfully. Then rewind, eject and raise the error; the operator starts over from the begin.
  - Writing at the begin also ends the data there (measured on the LTO-3, 2026-11-22: a read behind the new file 0 ends at
    the end of the data). The old files cannot be restored any more. It is not a secure erase.
  - `TOC_State.FAILED` exists already and the TOC format stays as it is.
  - Decided 2026-11-22: **the trailing TOC decides whether the files were restored.** The leading TOC only says whether
    something happened to the tape and what the chances are. It is not enough to call a restore good.
  - Best effort: if the drive does not take the write (or the host is gone), the leading TOC still says `IDLE` and only
    the missing trailing TOC shows it. That marker has to stay.
  - `dd` must run with `LC_ALL=C` so that the reason can be recognised. `TapeDrive.Write()` does not set it: on a German
    host `dd` says "Auf dem Gerät ist kein Speicherplatz mehr verfügbar" (checked 2026-11-22). `WriteRandom()` sets it already.
  - Decided 2026-11-22: the same steps run if a file (not only the trailing TOC) hits the end of the tape.
  - Decided 2026-11-22: **without the trailing TOC the tape is not valid.** The fallback of `ReadJob` to the copy in the TOC
    directory goes away. The operator does not know a TOC at all, only that the files are kept safely.
- **Job lists: look closely at the tasks the Job system works on.** The host calls `Read()` or `Write()`; the request is
  turned into a list of steps whose order is strictly defined by the context. The program, not the caller, is smart enough
  to start the right processes.

  ```
  Read():   Rewind(), ReadFile() -> TOC, for file in TOC.Files(): ReadFile(), ReadFile() -> TOC, Rewind(), Eject()
  Write():  Rewind(), ReadCM(), CreateTOC(), Write(TOC), Write(Folder[]), Write(TOC), Rewind(), Eject()
  if the trailing Write(TOC) fails and there is no space left:
            ClearTOCBody(), Rewind(), Eject(), RAISE ERROR
  ```

  - The TOC is a regular JSON file that is always written at the begin and at the end (hardcoded), by the same `Write()` /
    `Read()` as any other file.
  - For the failure list to reach the tape it needs a write in between. Proposal: `ClearTOCBody(), Rewind(), Write(TOC),
    Rewind(), Eject(), RAISE ERROR`.
  - `ReadCM()` is optional, as everything beyond the five basics (list of `nstX`, rewind, eject, dd in, dd out). Without
    a chip the list is the same.
  - A step on a file is chosen by the context:

    | Context | Write | Read |
    |---------|-------|------|
    | plain, no checksum | `WriteFile()` | `ReadFile()` |
    | plain, checksum | `CreateChecksum()` + `WriteFile()` | `ReadFileValidate()` |
    | encrypted, no checksum | `WriteEncryptFile()` | `ReadDecrypt()` |
    | encrypted, checksum | `CreateChecksum()` + `WriteEncryptFile()` | `ReadDecryptValidate()` |

  - With the TOC as it is, the checksums must be known before the leading TOC is written, so `CreateChecksum()` of all
    files comes before `CreateTOC()`.
  - The combined steps are pipes (`openssl | dd`). The exit code of a pipe is that of its last program, so a failing
    `openssl` could pass unnoticed and leave a truncated file on the tape. They need `pipefail` (bash, not `sh`) or two
    processes that are both checked.
  - Open: `Eject()` in the lists, on request only (as today) or always?
- **Research: everything in one go.** Make the checksum while reading, encrypt, and feed the tape so fast that it never
  stops. Measured on the LTO-8 (214 GB, 2026-11-20): the write job took 44 min and the restore 53 min, the tape alone needs
  about 16 min, because checksum, encryption and tape run one after the other.
  - **Decided 2026-11-20: the checksums go to the trailing TOC.** The leading TOC carries a *checksum scheme* that says
    "look in the trailer". So the tape can start as soon as the first file is encrypted, no barrier on all checksums.
    This replaces the rule "both TOCs are equivalent" (DESIGN.md) once it is built; the leading TOC then has the plan and
    the keys, not the checksums.
  - Every byte is read **at least twice**: (1) always, to make the checksum; (2) to write it, or to encrypt and write it.
    Reading twice is wanted: if the link to the SAN fails under the stress of the first read, a single pass would put
    corrupt data on the tape.
  - The spool is not stupid either, also if it is bigger than the tape (`LTO_CAP`): the tape needs the file locally
    anyway, with S3 in mind (`File.Get`). It needs a window (a limit of how many encrypted files may wait for the tape)
    and each `.crypt` is removed as soon as it is on the tape; today the spool holds everything until the end.
  - Checksum and encryption must each be skippable. Both on is the sensible default: in the enterprise world everything
    is taken out of the storage medium.
  - Resources are limited: fast storage for the spool is clear, but source, spool and tape share disks and link.
    The tape should be served first.
  - **Test plan (read only):** a large live VM disk on the big share (about 1 TiB). The checksum of a disk that a VM is
    writing to changes while it is read, so only `write()` and `encrypt() + write()` can be measured, not the integrity.
    Measure how long the tape is busy over the whole job.

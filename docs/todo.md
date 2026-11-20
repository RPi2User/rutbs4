# RUTBS-UI

- UI:           gtk4, tabs mit den Servern, XML-Viewer
- Backend:      network-daemon, checksumming, parallel
- Transport:    JSON-like API-Calls, Port 5533
- CLI:          

path, optimal-blocksize, ltoV (es könnten mehr als 1 drive/pc angeschlossen sein!)

- Drive state machine: ask the drive for its state before every action except trivial ones (CM read, status). Find the SCSI query that shows "busy" while a write runs. See DESIGN.md, "Drives".
- **RC:** Tape format with the bandwidth measurement / block size benchmark (destructive on purpose), result into the cartridge memory. See [TapeFormat.md](TapeFormat.md).
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

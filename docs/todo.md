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
  about 16 min, because checksum, encryption and tape run one after the other. Constraints that stay:
  - The checksum *should* be known from the start, because the full TOC is written first.
  - Reading the source twice is not stupid: if the link to the SAN fails under the stress of the first read, a single
    pass would put corrupt data on the tape. The first pass tests the source before the tape is touched.
  - The spool is not stupid either, also if it is bigger than the tape (`LTO_CAP`): the tape needs the file locally
    anyway, with S3 in mind (`File.Get`).
  - Checksum and encryption must each be skippable. Both on is the sensible default: in the enterprise world everything
    is taken out of the storage medium.
  - So the question is not "drop the passes" but how to keep the tape streaming (spool on fast storage, encrypt while
    the previous file is written, read back with decrypt and checksum in one pipe).

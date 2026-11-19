# RUTBS-UI

- UI:           gtk4, tabs mit den Servern, XML-Viewer
- Backend:      network-daemon, checksumming, parallel
- Transport:    JSON-like API-Calls, Port 5533
- CLI:          

figure out how to 


path, optimal-blocksize, ltoV (es könnten mehr als 1 drive/pc angeschlossen sein!)

- Drive state machine: ask the drive for its state before every action except trivial ones (CM read, status). Find the SCSI query that shows "busy" while a write runs. See DESIGN.md, "Drives".
- **RC:** Bandwidth measurement / block size benchmark for the loaded tape (destructive on purpose), first the benchmark alone, then its result into the cartridge memory (0x080B) and used by the write. See DESIGN.md, "Drives".

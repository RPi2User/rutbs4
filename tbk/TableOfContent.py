from tbk.File import File

class TableOfContent:

    files: list[File]
    ltoV : str
    bs: str
    tape_size : str
    tbkV : str
    last_mod : str

    def __init__(self, files: list[File], lto_version: str, optimal_blocksize: str, tape_sizeB: int, tbk_version: str, last_modified: str = "") -> None:
        self.files: list[File] = files      # List of all Files from TableOfContent
        self.ltoV: str = lto_version        # LTO-Version of Tape/Drive
        self.bs: str = optimal_blocksize    # Optimal Blocksize (only relevant for "dd")
        self.tape_size: int = tape_sizeB    # Constant, depends on LTO-Version
        self.tbkV: str = tbk_version        # Software-Version of Tape-Backup-Software from original TOC
        self.last_mod: str = last_modified  # Optional Timestamp (required for reading of tape)
        
    def __str__(self) -> str:
        return "TableOfContent(Files: " + str(self.files.__str__) + " LTO-Version: " + self.ltoV + " optimal Blocksize: " + self.bs + " Tape-Size: " + str(self.tape_size) + " TBK-Version" + self.tbkV + ")"
    
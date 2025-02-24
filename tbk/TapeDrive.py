import os

DEBUG: bool = False

class TapeDrive:
    
    def __init__(self, path_to_tape_drive: str, blocksize: str) -> None:
        self.bs: str = blocksize
        self.drive_path: str = path_to_tape_drive
        
    def write(self, path_to_file: str, quiet: bool) -> None:
        _ec: int = 0    # Exit-Code
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # dd if='" + path_to_file + "' of="+ self.drive_path + " bs=" + self.bs)
            print("Quiet: " + str(quiet))
            return
        if quiet:
            _ec = os.system("dd if='" + path_to_file + "' of="+ self.drive_path + " bs=" + self.bs + " 2>/dev/null")
        else:
            _ec = os.system("dd if='" + path_to_file + "' of="+ self.drive_path + " bs=" + self.bs + " status=progress")
        if _ec != 0:
            raise
        
    def read(self, path_to_file: str, quiet: bool) -> None:
        _ec: int = 0    # Exit-Code
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # dd if=" + self.drive_path + " of='"+ path_to_file + "' bs=" + self.bs)
            print("[DEBUG] Quiet: " + str(quiet))
            return
        if quiet:
            _ec = os.system("dd if=" + self.drive_path + " of='"+ path_to_file + "' bs=" + self.bs + " 2>/dev/null")
        else:
            _ec = os.system("dd if=" + self.drive_path + " of='"+ path_to_file + "' bs=" + self.bs + " status=progress")
        if _ec != 0:
            raise

    def dump_toc(self) -> None:
        _ec: int = 0    # Exit-Code
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # dd if=" + self.drive_path + " bs=" + self.bs + " | cat ")
        else:
            _ec = os.system("dd if=" + self.drive_path + " bs=" + self.bs + " | cat ")

        if _ec != 0:
            raise

    def rewind(self) -> None:
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # mt -f " + self.drive_path + " rewind")
        else:
            os.system("mt -f " + self.drive_path + " rewind")
        
    def eject(self) -> None:
        if DEBUG:
            print("[DEBUG] debug@tbk:~ # mt -f " + self.drive_path + " eject")
        else:
            os.system("mt -f " + self.drive_path + " eject")

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import tbk.TableOfContent as TableOfContent
import tbk.Status as Status
import tbk.File as File
from time import sleep
from functools import partial

class Command:

    # Vars
    pid: int = -1   # PID of cmd
    running: bool   # process running?
    io : str        # contents of /proc/<PID>/io
    io_path : str   # /proc/<PID>/io
    stdout: str     # current stdout of process
    stderr: str     # current stderr of process
    exitCode: int   # Exit-Code
    status_msg: str # Additional Stuff like known Error Messages 
    # --------------------------------------------------------------

    def __init__(self, cmd: str) -> None: 
        pass

    # This starts the process in the background
    def start(self) -> None:
        pass

    def calcChecksums(self, toc: TableOfContent, readWrite: bool) -> bool:
        max_threads = self.coreCount  # get the number of CPU threads
        _out: bool = True
        with ThreadPoolExecutor(max_threads) as executor:
            future_to_file = {executor.submit(partial(file.CreateChecksum, readWrite)): file for file in toc.files}
            
            for future in as_completed(future_to_file):
                file: File = future_to_file[future]
                try:
                    success = future.result()  # Wait for the checksum calculation to finish and get the result
                    if not success: 
                        self.status_msg = "[ERROR] Checksum MISMATCH for " + str(file)
                        self.status = Status.ERROR.value
                        _out = False
                except Exception as e:
                    self.status_msg = f"[ERROR] Exception during checksum calculation for {file}: {e}"
                    self.status = Status.ERROR.value
                    _out = False
        return _out
import subprocess
import json


class Command:

    """
    # --------------------------------------------------------------
    pid: int = -1   # PID of cmd
    running: bool   # process running?
    io : str        # contents of /proc/<PID>/io
    io_path : str   # /proc/<PID>/io
    stdout: str     # current stdout of process
    stderr: str     # current stderr of process
    exitCode: int   # Exit-Code
    status_msg: str # Additional Stuff like known Error Messages 
    # --------------------------------------------------------------
    """
    def __init__(self, cmd: str) -> None: 
        self.cmd = cmd
        self.process: subprocess.Popen = None
        self.pid: int = -1
        self.running: bool = False
        self.io: str = ""
        self.io_path: str = ""
        self.stdout: str = ""
        self.stderr: str = ""
        self.exitCode: int = None
        self.status_msg: str = ""

    # This starts the process in the background
    def start(self) -> None:
        self.process = subprocess.Popen(
            self.cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.pid = self.process.pid
        self.running = True
        self.io_path = f"/proc/{self.pid}/io"
        # Get Status of Process after spawn
        self.status()

    def kill(self) -> None:
        self.process.terminate()
        self.status()
    
    # This populates all Vars
    def status(self) -> None:
        pass

    def __str__(self):
        # Returns Command c in json
        self.status()
        data = {
            "cmd": self.cmd,
            "pid": self.pid,
            "running": self.running,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exitCode": self.exitCode
        }
        return json.dumps(data, indent=2)
"""
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
"""
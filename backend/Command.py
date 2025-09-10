import sys
import subprocess
import json
import threading

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
    def __init__(self, cmd: str, filesize: int = -1) -> None: 
        self.cmd = cmd
        self.process: subprocess.Popen = None
        self.pid: int = -1
        self.running: bool = False
        self.filesize: int = filesize
        self.io: List[str] = []      # noqa: F821
        self.io_path: str = ""
        self.stdout: List[str] = []  # noqa: F821
        self.stderr: List[str] = []  # noqa: F821
        self.exitCode: int = None
        self.status_msg: str = ""
        self.permError: bool = False


    # This starts the process in the background
    def start(self):
        if self.cmd == "":
            raise Exception("ERROR: Process cannot be initiated, command string empty")

        self.process = subprocess.Popen(
            self.cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.pid = self.process.pid
        self.running = True
        self.io_path = f"/proc/{self.pid}/io"

        # Get Status of Process after spawn
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.status()

    def _read_stdout(self):
        for line in self.process.stdout:
            self.stdout.append(line.rstrip('\n'))

    def _read_stderr(self):
        for line in self.process.stderr:
            self.stderr.append(line.rstrip('\n'))
        

    # Retruns Exitcode of application
    def kill(self) -> int:
        self.status()
        self.process.terminate()
        return self.process.wait()
        
    
    # This populates all Vars
    def status(self) -> None:
        if self.process is None:
            return

        # This kills the zombie process
        try:
            self.process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass

        if self.process.returncode is None:
            self.running = True
            data = {
                "cmd": self.cmd,
                "pid": self.pid,
                "running": self.running,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "filesize": self.filesize,
                "io": self.io,
                "exitCode": self.exitCode
            }

            print("DEBUG: cmd " + json.dumps(data)) # BUG zobie process wait(timeout=0.1) with exept subprocess.TimeoutExpired
            if not self.permError: 
                self._pollIOfile()
        
        else:
            self.running = False
            self.exitCode = self.process.returncode
            self.process = None

    def _pollIOfile(self) -> None:
        if not self.permError:
            try:
                with open(self.io_path, "r") as f:
                    self.io = [line.rstrip('\n') for line in f.readlines()]
            except PermissionError:
                print("[ERROR] Insufficient Permissions: Can't read file " + self.io_path, file=sys.stderr)
                self.permError = True

    def _asdict(self) -> dict:
        self.status()
        data = {
            "cmd": self.cmd,
            "pid": self.pid,
            "running": self.running,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "filesize": self.filesize,
            "io": self.io,
            "exitCode": self.exitCode
        }

        return data

    def __str__(self):
        # Returns Command json as str

        return json.dumps(self._asdict())
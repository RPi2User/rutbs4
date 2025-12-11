import sys
import subprocess
import json
import threading
from time import sleep
from typing import List

class Command:

    """
    # --------------------------------------------------------------
    pid: int = -1   # PID of cmd
    running: bool   # process running? -> TODO make ths a parameter!
    io : str        # contents of /proc/<PID>/io
    io_path : str   # /proc/<PID>/io
    raw: bool       # return stdout/stderr as hex
    stdout: str     # current stdout of process
    stderr: str     # current stderr of process
    exitCode: int   # Exit-Code
    status_msg: str # Additional Stuff like known Error Messages 
    # --------------------------------------------------------------
    """
    def __init__(self, cmd: str, filesize: int = -1, raw: bool = False) -> None: 
        self.quiet: bool = False
        self.cmd = cmd
        self.filesize: int = filesize
        self.raw: bool = raw
        self.running: bool = False
        
        self.clearCommand()
        
    def wait(self, timeout: int = 100) -> None:
        self.status()
        
        if not self.running:
            self.start()
        
        if timeout == 0:
            while self.running:
                sleep(.01)
                self.status()
        
        if timeout != 0:
            for n in range(timeout):
                sleep(.01)
                self.status()
            self.kill()
            self.status()

    def clearCommand(self)-> None:
        self.process: subprocess.Popen = None
        self.pid: int = -1
        
        self.io: List[str] = []
        self.io_path: str = ""
        self.stdout: List[str] = []
        self.stderr: List[str] = []
        self.exitCode: int = -1
        self.status_msg: str = ""
        self.permError: bool = False

    # This starts the process in the background
    def start(self):
        self.clearCommand()
        if self.cmd == "":
            raise ValueError("ERROR: Process cannot be initiated, command string empty")

        self.process = subprocess.Popen(
            args=self.cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )
        self.pid = self.process.pid
        self.running = True
        self.io_path = f"/proc/{self.pid}/io"

        # Get Status of Process after spawn
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.status()
        if not self.quiet:
            print("[EXEC] " + json.dumps(self._asdict(), indent=2))

    def _read_stdout(self):
        # Some commands may print raw binary, those can't be interpreted as UTF-8
        _raw: str = ""
        for element in self.process.stdout:
            if self.raw:
                _raw += f"{element.hex()}"
            else:
                self.stdout.append(element.decode('utf-8').rstrip('\n'))

        if self.raw: 
            self.stdout.append(_raw)

    def _read_stderr(self):
        _raw: str = ""
        for element in self.process.stderr:
            if self.raw:
                _raw += f"{element.hex()}"
            else:
                self.stderr.append(element.decode('utf-8').rstrip('\n'))
                
        if self.raw: 
            self.stderr.append(_raw)
        

    # Retruns Exitcode of application
    def kill(self) -> int:
        self.status()
        if (self.process):
            self.process.terminate()
            return self.process.wait()
        return 0
        
    
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
            # BUG zobie process wait(timeout=0.1) with exept subprocess.TimeoutExpired
            
            if not self.permError: 
                self._pollIOfile()
        
        else:
            self.running = False
            self.exitCode = self.process.returncode
            self.process.kill()

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
        return json.dumps(self._asdict())
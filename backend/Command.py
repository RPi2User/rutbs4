import os
import signal
import sys
import subprocess
import json
import threading
from time import sleep
from typing import List

class Command:

    """
    #### === COMMAND ==============================================================================

    - Command.__init__()
        - Requires
            - The command e.g. "cat foo.txt"
        - Supports
            - Filesize
            - Binary / RAW output (0xa5 6a -> "a56a")
    
    | `Command.`             | Description                                                            |
    |------------------------|------------------------------------------------------------------------|
    | `Command.start()`      | Starts the command in the background                                   |
    | `Command.wait()`       | Blocks until command has exited                                        |
    | `Command.kill()`       | Blocks until command is killed (SIGTERM, timeout 100ms)                |
    | `Command.cleanup()`    | Get called before running ← false, does close STDOUT/STDERR            |
    | `Command.reset()`      | Calls self.cleanup() and clears all vars EXCEPT cmd, filesize and raw  |
    | `Command.status()`     | Refreshes all vars, always call this!                                  |

    ### --- VARIABLES -----------------------------------------------------------------------------

    **Core Variables:**
    | Var            | Type               | Description                                                |
    |----------------|--------------------|------------------------------------------------------------|
    | `self.process` | `subprocess.Popen` | MAIN INTERFACE, process instance for OS communication      |
    | `self.cmd`     | `str`              | Main command string                                        |
    | `self.running` | `bool`             | Set by `wait()` or `start()`, cleared by `self.refresh()`  |
    | `self.pid`     | `int`              | Process ID provided by `self.process`                      |

    **Command Results**
    | Var              | Type         | Description                  |
    |------------------|--------------|------------------------------|
    | `self.stdout`    | `List[str]`  | All lines of STDOUT          |
    | `self.stderr`    | `List[str]`  | All lines of STDERR          |
    | `self.exitCode`  | `int`        | Exit code of `self.process`  |

    **Block I/O (Disk or Tape)**
    | Var              | Type         | Description                          |
    |------------------|--------------|--------------------------------------|
    | `self.io_path`   | `str`        | Path to the file: `"/proc/<PID>/io"` |
    | `self.io`        | `List[str]`  | Content of the `/proc/<PID>/io` file |

    **Object-Related Variables**
    | Var               | Type        | Description                                         |
    |-------------------|-------------|-----------------------------------------------------|
    | `self.quiet`      | `bool`      | If `True`, prints `str(self)` in a pretty format    |
    | `self.status_msg` | `List[str]` | Message string for error handling                   |
    | `self.permError`  | `bool`      | Set if the backend lacks permission to read a file  |
    | `self.didRun`     | `bool`      | Tracks whether the command has already been started |
    | `self.closed`     | `bool`      | Monitors whether STDIN or STDOUT streams are closed |

    Are self.didRun and self.closed equal?
    - No!

    When you run c multiple times you see:
    1. iteration:
        - self.running == True:
            - didRun := False, closed := False
        - Command complete:
            - didRun := True, closed := True
    2. iteration:
        - self.running == True: 
            - didRun := True, closed := False
        - Command complete:
            - didRun := True, closed := True
    
    self.didRun is a "sticky bit" that shows if a cmd got exectuted AT LEAST ONCE
    """

    def __init__(self, cmd: str, filesize: int = -1, raw: bool = False) -> None:
        self.cmd: str = cmd
        self.filesize: int = filesize
        self.raw: bool = raw
        self._clear() # This defaults all vars :3

# --- PUBLIC FUNCTIONS ----------------------------------------------------------------------------

    def start(self):
        if self.cmd == "":
            # Constructor needs a string but a literal "" is valid, but not for me!
            raise ValueError("ERROR: Process cannot be initiated, command string empty")

        self.process = subprocess.Popen(
            args="exec " + self.cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )
        self.closed = False
        self.pid = self.process.pid
        self.running = True
        self.didRun = True
        self.io_path = f"/proc/{self.pid}/io"

        # Get Status of Process after spawn
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.status()
        if not self.quiet:
            print("[EXEC] " + json.dumps(self._asdict(), indent=2))

    def wait(self, timeout: int = 0) -> None:
        """
        Command.wait(timeout=XXX)
        This wait for Command to complete or terminates the process if Timeout is reached
        - Does start the process if needed
        - Timeout is N in 10ms
        - Command.reset() needed when restarting a process

        Command("sleep 10").wait(500) -> Does wait for 5000ms (5sec) until this process gets terminated
        Command.status_msg will contain the "Timeout reached" string

        Three Design scenarios:
        1. Command finishes semi-instant (run time <10ms)
        2. Command runs as long as it takes (like a dd process) -> timeout=0, inf. runtime, DEFAULT
        3. Command needs to finish within n * 10 ms
        """

        # Start only if process did not run prior
        if not self.didRun:
            self.start()

        sleep(.01)      # Wait 10ms for early completion
        self.status()   # Fill status vars

        if not self.running:    # Case 1)   Process finishes semi-instant
            return

        if timeout == 0:        # Case 2)   inf. loop until process finishes
            while self.running:
                sleep(.01)
                self.status()
            return

        if timeout != 0:        # Case 3)   Command.kill() on timeout reached
            for n in range(timeout - 1):    # minus first one from 1)
                self.status()
                if not self.running:
                    return
                sleep(.01)
            self.kill()
            self.status_msg.append("Timeout reached, process killed")
            self.status()

    def kill(self) -> None:
        self.status()
        if self.process:
            try:
                os.kill(self.pid, signal.SIGTERM)
                self.exitCode = self.process.wait()
                self.status()
            except Exception as e:
                self.status_msg.append(f"[ERROR] killing process: {str(e)}")

    def cleanup(self) -> None:
        if self.process and not self.closed:
            self.process.stdout.close()
            self.process.stderr.close()
            self.process.wait()
            self.closed = True

    def reset(self) -> None:
        self.cleanup()
        self._clear()

    # This populates all Vars
    def status(self) -> None:
        if self.process is None:
            return

        if self.process.poll() is None:
            self.running = True

            if not self.permError: 
                self._pollIOfile()
        else:
            self.running = False
            self.exitCode = self.process.returncode
            self.cleanup()

    def _asdict(self) -> dict:
        self.status()
        data = {
            "cmd": self.cmd,
            "pid": self.pid,
            "running": self.running,
            "quiet": self.quiet,

            "process": str(type(self.process)),
            "closed": self.closed,
            "did_ran": self.didRun,
            "status_msg": self.status_msg,

            "filesize": self.filesize,
            "permission_error": self.permError,
            "io_path": self.io_path,
            "io": self.io,

            "raw": self.raw,
            "exitCode": self.exitCode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        return data

    def __str__(self):
        if self.quiet:
            return json.dumps(self._asdict())
        return json.dumps(self._asdict(), indent=2)

# --- PRIVATE FUNCTIONS ---------------------------------------------------------------------------

    def _clear(self) -> None:
        # This clears ALL VARIABLES to default
        # ONLY if self.cleanup() was called!

        self.pid: int = -1
        self.running: bool = False
        self.quiet: bool = True
        self.process: subprocess.Popen = None

        self.closed: bool = True
        self.didRun: bool = False
        self.status_msg: List[str] = []

        self.permError: bool = False
        self.io: List[str] = []
        self.io_path: str = ""

        self.exitCode: int = -1
        self.stdout: List[str] = []
        self.stderr: List[str] = []

    def _pollIOfile(self) -> None:
        if not self.permError:
            try:
                with open(self.io_path, "r") as f:
                    self.io = [line.rstrip('\n') for line in f.readlines()]
            except PermissionError:
                self.status_msg.append("[INFO] Insufficient Permissions: Can't read file " + self.io_path)
                self.permError = True

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
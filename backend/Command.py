import sys
import subprocess
import json
import threading
from time import sleep
from typing import List

class Command:

    def __init__(self, cmd: str, filesize: int = -1, raw: bool = False) -> None:
        """
        === COMMAND ===============================================================================
        - Command.__init__             Needs:
                                       - The command e.g. "cat foo.txt"
                                       Supports:
                                       - Filesize
                                       - Binary / RAW output (0xa5 6a -> "a56a")
        - Command.start                Starts the command in the background
        - Command.wait                 Blocks until command has exited
        - Command.kill                 Blocks until command is killed (SIGTERM, timeout 100ms)
        - Command.cleanup              Get called before running ← false, does close STDOUT/STDERR
        - Command.reset                Calls self.cleanup() and clears all vars EXCEPT cmd, filesize and raw
        - Command.status               Refreshes all vars, always call this!
        """

        """
        --- PARAMETER -----------------------------------------------------------------------------
        Core vars
        - self.process: subprocess.Popen      MAIN INTERFACE, process instance for OS Comms
        - self.cmd: str                       Main command string
        - self.running: bool                  wait() or start() sets it, self.refresh() clears it
        - self.pid: int                       Process ID given from self.process

        Command results
        - self.stdout: List[str]              ALL lines of STDOUT
        - self.stderr: List[str]              ALL lines of STDERR
        - self.exitCode: int                  ExitCode of self.process

        Block I/O (disk or tape)
        - self.io_path: str                   "/proc/<PID>/io"
        - self.io: List[str]                  Content of /proc/<PID>/io file

        Object related vars
        - self.quiet: bool                    true: prints str(self) in pretty
        - self.status_msg: str                message string for error handling
        - self.permError: bool                Gets set if backend has no permission on reading a file
        - self.didRan: bool                   Did we start the command already?!
        - self.closed: bool                   Watches if STDIN / STDOUT is closed
        """

        # Constructor logic
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
            args=self.cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )
        self.closed = False
        self.pid = self.process.pid # BUG Wrong PID, only getting PID of "$ sh -c <exec>" cmd and NOT pid(<exec>)
        self.running = True
        self.didRan = True
        self.io_path = f"/proc/{self.pid}/io"

        # Get Status of Process after spawn
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.status()
        if not self.quiet:
            print("[EXEC] " + json.dumps(self._asdict(), indent=2))

    def wait(self, timeout: int = 100) -> None:
        self.status()

        if not self.didRan:
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

    # Retruns Exitcode of application
    def kill(self) -> int:
        self.status()
        if (self.process):
            self.process.terminate()
            return self.process.wait()
        return 0

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

    def _asdict(self) -> dict:
        self.status()
        data = {
            "cmd": self.cmd,
            "pid": self.pid,
            "running": self.running,
            "quiet": self.quiet,

            "process": str(type(self.process)),
            "closed": self.closed,
            "did_ran": self.didRan,
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
        self.didRan: bool = False
        self.status_msg: str = ""

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
                print("[ERROR] Insufficient Permissions: Can't read file " + self.io_path, file=sys.stderr)
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
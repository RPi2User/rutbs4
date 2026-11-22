import os
import signal
import subprocess
import json
import threading
import time
from typing import List

class Command:

    """
    #### === COMMAND ==========================================================

    Command.__init__(cmd: str, filesize: int = -1, raw: bool = False, env: dict = None, stdin: bytes = None):
    - Requires
        - The command e.g. "cat foo.txt"
    - Supports
        - Filesize
        - Binary / RAW output (0xa5 6a -> "a56a")
        - env: extra environment variables, the place for secrets.
               They never show up in `ps`, _asdict() or str()
        - stdin: bytes for the standard input, e.g. a TOC that goes through `openssl`.
               Written by a thread (a big input and a big output cannot block each other), then
               the input is closed. It may hold secrets: it never shows up in `ps`, _asdict()
               or str() (only its size), and it is released once handed to the process, so
               a second run needs a new Command. Without `stdin` the input is /dev/null, so a
               command that reads it ends at once instead of waiting for a terminal.

    Command.quote(text) wraps a path in single quotes for the command string.
    
    A Command only describes and observes a process. It is started by `Job` and nobody else:
    `Job.Add()` for queued work, `Job.Run()` for a small request that is needed at once.

    | `Command.`             | Description                                                            |
    |------------------------|------------------------------------------------------------------------|
    | `Command.start()`      | Starts the command in the background, ONLY `Job` calls this            |
    | `Command.kill()`       | SIGTERM to the process group, after `KILL_GRACE` SIGKILL, then gives up |
    | `Command.cleanup()`    | Get called before running ← false, does close STDOUT/STDERR            |
    | `Command.reset()`      | Calls self.cleanup() and clears all vars EXCEPT cmd, filesize, raw, env (stdin is gone after a run) |
    | `Command.status()`     | Refreshes all vars, always call this!                                  |

    ### --- VARIABLES ---------------------------------------------------------

    **Core Variables:**
    | Var            | Type               | Description                                                |
    |----------------|--------------------|------------------------------------------------------------|
    | `self.process` | `subprocess.Popen` | MAIN INTERFACE, process instance for OS communication      |
    | `self.cmd`     | `str`              | Main command string                                        |
    | `self.running` | `bool`             | Set by `wait()` or `start()`, cleared by `self.refresh()`  |
    | `self.pid`     | `int`              | Process ID provided by `self.process`                      |
    | `self.readers` | `List[Thread]`     | STDOUT/STDERR reader and STDIN writer, joined by `cleanup()` |
    | `self.stdinSize` | `int`            | Size of the given stdin in bytes, `-1` if there was none   |

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
    | `self.killed`     | `bool`      | `Job` killed it because its deadline was over       |
    | `self.signalled`  | `bool`      | `kill()` was called while it ran                    |
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

    KILL_GRACE: float = 0.1     # seconds to wait after SIGTERM, and again after SIGKILL

    def __init__(self, cmd: str, filesize: int = -1, raw: bool = False, env: dict = None, stdin: bytes = None) -> None: # type: ignore
        self.cmd: str = cmd
        self.stdin: bytes | None = stdin        # released by start(), see the class doc
        self.stdinSize: int = -1 if stdin is None else len(stdin)
        self.filesize: int = filesize
        self.raw: bool = raw
        self.env: dict = env or {}
        self._clear() # This defaults all vars

    @staticmethod
    def quote(text: str) -> str:
        # 'it's' -> 'it'\''s', so any path survives the shell
        return "'" + text.replace("'", "'\\''") + "'"

# --- PUBLIC FUNCTIONS ----------------------------------------------------------------------------

    def start(self):
        if self.cmd == "":
            # Constructor needs a string but a literal "" is valid, but not for me!
            raise ValueError("ERROR: Process cannot be initiated, command string empty")

        data: bytes | None = self.stdin
        self.stdin = None       # secrets are not kept longer than needed

        self.process = subprocess.Popen(
            args="exec " + self.cmd,
            shell=True,
            stdin=subprocess.DEVNULL if data is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,     # its own process group, kill() reaches every program of a pipe
            text=False,
            env={**os.environ, **self.env}
        )
        self.closed = False
        self.pid = self.process.pid
        self.running = True
        self.didRun = True
        self.io_path = f"/proc/{self.pid}/io"

        # Get Status of Process after spawn
        self.readers = [threading.Thread(target=self._read_stdout, daemon=True),
                        threading.Thread(target=self._read_stderr, daemon=True)]
        if data is not None:
            self.readers.append(threading.Thread(target=self._write_stdin, args=(data,), daemon=True))
        for reader in self.readers:
            reader.start()
        self.status()
        if not self.quiet:
            print("[EXEC] " + json.dumps(self._asdict(), indent=2))

    def kill(self) -> None:
        """
        Never blocks longer than 2 * KILL_GRACE, plus what `cleanup()` waits for the readers. The whole process group
        is killed, so also every program of a pipe. A process in uninterruptible sleep (hung mount,
        busy drive) survives even SIGKILL: it is given up and `running` stays True until it is gone.
        """
        self.status()
        if self.running:    # never signal a finished PID, the kernel may have reused it
            self.signalled = True
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self.pid, sig)
                except ProcessLookupError:
                    break
                except OSError as e:
                    self.status_msg.append(f"[ERROR] killing process: {str(e)}")
                    break
                end: float = time.monotonic() + self.KILL_GRACE
                while self._alive() and time.monotonic() < end:
                    time.sleep(0.005)
                if not self._alive():
                    break
        self.status()

    def _alive(self) -> bool:
        """The process runs. After a kill also: any other program of its group, the shell of a pipe may end first."""
        if self.process.poll() is None:
            return True
        if not self.signalled:
            return False
        try:
            os.killpg(self.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return True

    def cleanup(self) -> None:
        if self.process and not self.closed:
            for reader in self.readers:     # read STDOUT/STDERR completely before closing
                reader.join(timeout=1)
            if not any(reader.is_alive() for reader in self.readers):   # closing what a thread still reads would block for good
                self.process.stdout.close() # type: ignore
                self.process.stderr.close() # type: ignore
            self.process.wait()
            self.closed = True

    def reset(self) -> None:
        self.cleanup()
        self._clear()

    def status(self) -> None:
        if self.process is None or (self.closed and not self.running):
            return      # not started, or its result is taken already

        if self._alive():
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
            "killed": self.killed,
            "status_msg": self.status_msg,

            "filesize": self.filesize,
            "stdin_bytes": self.stdinSize,
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
        return json.dumps(self._asdict(), indent=2)

# --- PRIVATE FUNCTIONS ---------------------------------------------------------------------------

    def _clear(self) -> None:
        # This clears ALL VARIABLES to default
        # ONLY if self.cleanup() was called!

        self.pid: int = -1
        self.running: bool = False
        self.quiet: bool = True
        self.process: subprocess.Popen = None # type: ignore
        self.readers: List[threading.Thread] = []

        self.closed: bool = True
        self.didRun: bool = False
        self.killed: bool = False
        self.signalled: bool = False
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
            except (FileNotFoundError, ProcessLookupError):
                pass    # ended meanwhile, or killed while another program of its pipe is still there

    def _write_stdin(self, data: bytes) -> None:
        try:
            self.process.stdin.write(data)  # type: ignore
        except OSError:
            pass    # the process ended (or was killed) before it read everything: its exit code tells
        finally:
            try:
                self.process.stdin.close()  # type: ignore
            except OSError:
                pass

    def _read_stdout(self):
        self._read(self.process.stdout, stderr=False)   # type: ignore

    def _read_stderr(self):
        self._read(self.process.stderr, stderr=True)    # type: ignore

    def _read(self, stream, stderr: bool) -> None:
        out: List[str] = self.stderr if stderr else self.stdout
        name: str = "STDERR" if stderr else "STDOUT"
        parts: List[str] = []   # raw output is joined once at the end: `+=` on a big string is quadratic

        for element in stream:
            if self.raw:
                parts.append(element.hex())
                continue
            try:
                out.append(element.decode('utf-8').rstrip('\n'))
            except UnicodeDecodeError:
                self.status_msg.append("[ERROR] String cannot be parsed, " + name + " converted to hex")
                self.raw = True
                self._convertToRaw(element, stderr=stderr)

        if parts:
            out[:] = [(out[0] if out else "") + "".join(parts)]

    def _convertToRaw(self, element: bytes, stderr: bool = False) -> None:
        _tmp: List[str] = []
        _current: str = ""

        if not stderr:
            _tmp = self.stdout
        else:
            _tmp = self.stderr

        for line in _tmp:
            _current += ''.join(format(char, '02x') for char in line.encode('utf-8'))
            _current += "0a"   # this adds the line terminator, which was prior the list seperator
        _current += ''.join(format(byte, '02x') for byte in element)

        _tmp.clear()    # delete all encoded data
        _tmp.append(_current)   # append all data

        if not stderr:
            self.stdout = _tmp
        else:
            self.stderr = _tmp
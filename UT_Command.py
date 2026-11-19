import json
import os
import unittest
from time import sleep, time

# Module imports
from backend.Command import Command
from backend.Job import EntryState, Job


class UT_Command(unittest.TestCase):

    AA_CREATE: str = ""
    AB_VAL: str = ""
    AC_START: str = "pwd"
    AD_BACK: str = "ping localhost -c 2"
    AE_WAIT: str = "ping localhost -c 2"
    AF_STDOUT: str = "echo b32fea58-45ec-4276-a129-ee4f1ee441ae"
    AG_STDERR: str = "echo b32fea58-45ec-4276-a129-ee4f1ee441ae 1>&2"
    AH_DD128MIB: str = "dd if=/dev/urandom of=/dev/null bs=1M count=128"
    AI_DD256MIB: str = "dd if=/dev/urandom of=/dev/null bs=1M count=256"
    AJ_WAITTIME: str = "ping localhost -c 10"
    AK_KILL: str = "ping localhost"
    AL_HEXOUT: str = "dd if=/dev/urandom bs=512 count=1 2>/dev/null"
    AN_CLEANUP: str = "echo 0"
    AN_CLEANUP1: str = "echo the quick brown fox jumps over the lazy dog"
    AO_RAW_NL: str = "cat /mnt/daten/testfiles/rutbs4/cmd/00_0f.txt" 
    AP_RAW_EXTREME: str = "cat /mnt/daten/testfiles/rutbs4/cmd/00_ff.txt"
    AR_RAW_ALLERR: str = ">&2 cat /mnt/daten/testfiles/rutbs4/cmd/00_ff.txt"

    RUN_MS: int = 60000     # deadline for tests whose runtime does not matter

    """_summary_
    Depdencies:
    - your favorite flavour of LINUX
    - pwd
    - ping
    - dd
    - printf
    """

    def test_AA_create(self) -> None:
        """
        Creates a Command object and tests:
            - c is a Object of "Command"
            - c.toString() will raise an Exception
            - c is cleaned successfully
        """
        c: Command = Command(self.AA_CREATE)    # Calls constructor
        str(c)                                  # Tests c.toString()

        self.assertEqual(type(c), Command)
        self.assertEqual(c.closed, True)
        print(".A_CREATE")

    def test_AB_validation(self) -> None:
        """
        Creates a Command object and tests all of the above and:
            - c has all default parameters
            - c.start() does raise the correct exception
        """

        c: Command = Command(self.AB_VAL)

        self.assertEqual(c.cmd, self.AB_VAL)
        self.assertEqual(c.pid, -1)
        self.assertEqual(c.running, False)
        self.assertEqual(c.stdout, [])
        self.assertEqual(c.stderr, [])
        self.assertEqual(c.filesize, -1)
        self.assertEqual(c.io, [])
        self.assertEqual(c.exitCode, -1) # TODO Add new vars!

        try:
            c.start()
            self.fail("[FAIL] NO EXCEPTION RAISED! Specific ValueError excpected!")
        except Exception as e:
            self.assertEqual(type(e), ValueError)
            self.assertEqual(e.args[0], "ERROR: Process cannot be initiated, command string empty")

        print("B_VAL")

    def test_AC_start(self) -> None:
        """
        This will test if the "pwd" command works on the machine.
            - pwd shall complete instant
            - for un-godly slow Systems a 100ms sleep is included but always not needed
            - my premise is that the command is finished after c.start().status() get called
            - this does not test concurrency!
        Test flow:
            1. create c with "pwd"
            2. start c
            3. sleep 100ms (for very slow systems)
            4. refresh all states from c
            5. Check Params:
                - c.cmd == "pwd"
                - c.pid != 0
                - c.exitCode == 0
            6. cleanup
        """

        c: Command = Command(self.AC_START)
        c.start()

        sleep(.1)
        str(c)  # trigger state refresh

        self.assertEqual(c.cmd, self.AC_START)
        self.assertNotEqual(c.pid, 0)
        self.assertEqual(c.exitCode, 0)

        c.cleanup()
        print("C_START")

    def test_AD_start(self) -> None:
        """
        Non-blocking capability
        This test checks if c is non-blocking and thus is truely in the background
        I choose a ping of localhost, a bit risky:
            1. ping might not be installed on your system
            2. your DNS config may not resolve localhost to ::1 or 127.0.0.1
        But:
            1. ping is quite universal and almost always installed
            2. localhost supports IPv4 and IPv6
            3. Does not rely on any hardware (except for a loopback device)

        Tests:
            1. If c is running in the background
            2. Gets a PID
            3. Validates PID with the existance of a IO-File from /proc/PID/io

        If 2. & 3. passes then we know the KERNEL did smth. for us

        Expected Results:
        - exitCode == 0
        - running == False
        - didRun == True
        - cloesed == True

        Does NOT test:
            - validate stdout/stderr
            - Job.Run()
        """

        c: Command = Command(self.AD_BACK)
        c.start() # c.start() blocks until most vars are populated

        # Startup validation
        self.assertEqual(c.cmd, self.AD_BACK)
        self.assertEqual(c.running, True)
        self.assertNotEqual(c.pid, 0)
        self.assertEqual(c.exitCode, -1)    # command shall not be exited
        self.assertNotEqual(c.io, [])       # the io file must have some content

        # Wait for command exit
        while c.running:
            sleep(.1)
            str(c)

        # Exit validation
        self.assertEqual(c.running, False)
        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.didRun, True)
        self.assertEqual(c.closed, True)

        print("D_START_WAIT")

    def test_AE_Wait(self) -> None:
        """
        Does the same as AD but instead of the while loop it uses Job.Run()
        """

        c: Command = Command(self.AE_WAIT)
        self.assertEqual(c.cmd, self.AE_WAIT)
        Job.Run(c, self.RUN_MS)

        # Exit validation
        self.assertNotEqual(c.pid, 0)
        self.assertEqual(c.running, False)
        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.didRun, True)
        self.assertEqual(c.closed, True)

        print("E_WAIT")

    def test_AF_STDOUT(self) -> None:
        """
        Test if command successfully writes test UUID to STDOUT
        """

        c: Command = Command(self.AF_STDOUT)
        self.assertEqual(c.cmd, self.AF_STDOUT)
        Job.Run(c, self.RUN_MS)

        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.stdout[0], "b32fea58-45ec-4276-a129-ee4f1ee441ae")
        self.assertEqual(c.stderr, [])
        print("F_STDOUT")

    def test_AG_STDERR(self) -> None:
        """
        Test if command successfully writes test UUID to STDERR
        """

        c: Command = Command(self.AG_STDERR)
        self.assertEqual(c.cmd, self.AG_STDERR)
        Job.Run(c, self.RUN_MS)

        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.stdout, [])
        self.assertEqual(c.stderr[0], "b32fea58-45ec-4276-a129-ee4f1ee441ae")
        print("G_STDERR")

    def test_AH_IO(self) -> None:
        """
        In order to test the IO capabilities we need a command that read/writes some data
        Hence I have some experience with dd I choose this dd command:

            dd if=/dev/urandom of=/dev/null bs=1M count=128

        So we expect like 130MB of data being read from /dev/urandom 
        and ~130MB should be written to /dev/null

        The I/O File should look like this:

            rchar: 121647344
            wchar: 121634816
            syscr: 135
            syscw: 116
            read_bytes: 0
            write_bytes: 0
            cancelled_write_bytes: 0

        rchar&wchar must be 
        - greater than 100MiB (100000000)
        - less than 150MiB (150000000)

        rest is irrelevant.

        Why do we check if less then 128MiB are written/read?
        > Since we POLL the I/O-File there is only a couple of chances to read the file.
        > The file is not available when the command is exited

        """
        c: Command = Command(self.AH_DD128MIB)
        self.assertEqual(c.cmd, self.AH_DD128MIB)
        Job.Run(c, self.RUN_MS)

        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.stdout, [])  # dd writes to stderr everything

        UPPER: int = 150000000
        LOWER: int = 100000000

        rchar_val: int = int(c.io[0].split(":")[-1].strip())
        wchar_val: int = int(c.io[1].split(":")[-1].strip())

        self.assertGreater(rchar_val, LOWER)
        self.assertGreater(wchar_val, LOWER)

        self.assertLess(rchar_val, UPPER)
        self.assertLess(wchar_val, UPPER)

        print("H_IO")

    def test_AI_IO_256(self) -> None:
        """
        Test IO of 256 MiB File Transfer with 50 MByte of tolerance
        """
        c: Command = Command(self.AI_DD256MIB)
        self.assertEqual(c.cmd, self.AI_DD256MIB)
        Job.Run(c, self.RUN_MS)

        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.stdout, [])  # dd writes to stderr everything

        UPPER: int = 275000000
        LOWER: int = 225000000

        rchar_val: int = int(c.io[0].split(":")[-1].strip())
        wchar_val: int = int(c.io[1].split(":")[-1].strip())

        try:
            self.assertGreater(rchar_val, LOWER)
            self.assertGreater(wchar_val, LOWER)

            self.assertLess(rchar_val, UPPER)
            self.assertLess(wchar_val, UPPER)

        except AssertionError:
            c.quiet = False
            print(c)
            raise

        print("I_IO_256")

    def test_AJ_Deadline(self) -> None:
        """
        Job.Run() kills a Command that is not finished in time:
            - returns after the deadline (1 s), not after the ping (10 s)
            - Command.killed, status_msg says why, the exit code is not 0
            - the Entry is KILLED, which is not FAILED
        """

        c: Command = Command(self.AJ_WAITTIME)
        self.assertEqual(c.cmd, self.AJ_WAITTIME)

        beg_time = time()
        Job.Run(c, deadlineMs=1000)
        end_time = time()

        try:
            self.assertGreater((end_time - beg_time), 0.9)
            self.assertLess((end_time - beg_time), 1.5)
            self.assertEqual(c.killed, True)
            self.assertEqual(len(c.status_msg), 1)
            self.assertIn("Deadline of 1000 ms exceeded", c.status_msg[0])
            self.assertNotEqual(c.exitCode, 0)
            self.assertEqual(c.running, False)
            entry = [e for e in Job.urgent if e.command is c][0]
            self.assertIs(entry.state, EntryState.KILLED)
        except AssertionError:
            c.quiet = False
            print(c)
            raise

        print("J_DEADLINE")

    def test_AJ_Urgent(self) -> None:
        """A quick Command is COMPLETED, not killed, and does not need the scheduler"""
        beg_time = time()
        c: Command = Job.Run(Command(self.AF_STDOUT))
        self.assertLess(time() - beg_time, 0.5)
        self.assertEqual(c.stdout[0], "b32fea58-45ec-4276-a129-ee4f1ee441ae")
        self.assertEqual(c.killed, False)
        self.assertEqual([e for e in Job.urgent if e.command is c][0].state, EntryState.COMPLETED)
        print("J_URGENT")

    def test_AK_Kill(self) -> None:
        """
        Spawns a endless ping on localhost and kills it
        """

        c: Command = Command(self.AK_KILL)
        self.assertEqual(c.cmd, self.AK_KILL)

        c.start()
        sleep(2)
        c.kill()

        try:
            self.assertNotEqual(c.exitCode, 0)
            self.assertEqual(c.running, False)
            self.assertEqual(c.closed, True)
            self.assertEqual(len(c.status_msg), 0)
            self.assertEqual(c.didRun, True)
        except AssertionError:
            c.quiet = False
            print(c)
            raise

        print("K_KILL")

    def test_AL_HEXOUT(self) -> None:
        """
        Tests if command supports hex output properly
        """

        c: Command = Command(self.AL_HEXOUT, raw=True)
        Job.Run(c, self.RUN_MS)

        try:
            self.assertEqual(len(c.status_msg), 0)
            self.assertEqual(c.cmd, self.AL_HEXOUT)
            self.assertEqual(c.raw, True)
            self.assertEqual(c.didRun, True)
            self.assertNotEqual(len(c.stdout), 0)   # stdout shall not be empty
            self.assertEqual(len(c.stderr), 0)      # stderr shall not have any data

        except AssertionError:
            c.quiet = False
            print(c)
            raise

        print("L_HEXOUT")

    def test_AM_HEXERR(self) -> None:
        """
        Same as AL_HEXOUT but now looking if exception Handling is done properly
        - c.status_msg must contain a error Message
        """

        c: Command = Command(self.AL_HEXOUT)
        Job.Run(c, self.RUN_MS)

        try:
            self.assertNotEqual(len(c.status_msg), 0)
            self.assertEqual(c.cmd, self.AL_HEXOUT)
            self.assertEqual(c.raw, True)
            self.assertEqual(c.didRun, True)
            self.assertNotEqual(len(c.stdout), 0)   # stdout shall not be empty
            self.assertEqual(len(c.stderr), 0)      # stderr shall not have any data

        except AssertionError:
            c.quiet = False
            print(c)
            raise

        print("M_HEXERR")

    def test_AN_cleanup(self) -> None:
        # This tests Command.reset() clears stdout
        c: Command = Job.Run(Command(self.AN_CLEANUP), self.RUN_MS)
        try:
            self.assertEqual(c.stdout[0], "0")
            c.reset()
            self.assertEqual((c.stdout, c.didRun, c.exitCode), ([], False, -1))
            c.cmd = self.AN_CLEANUP1
            c.start()                   # Command level test: reset() makes the same object startable again
            while c.running:
                sleep(.01)
                c.status()
            self.assertNotEqual(c.stdout[0], "0")

        except AssertionError:
            c.quiet = False
            print(c)
            raise

        print("N_CLEAN")

    def test_AO_rawWithNewLines(self) -> None:
        c: Command = Command(self.AO_RAW_NL, raw=True)

        Job.Run(c, self.RUN_MS)

        try:
            self.assertEqual(len(c.stdout), 1)
            self.assertEqual(len(c.stderr), 0)
            self.assertEqual(c.exitCode, 0)
            self.assertEqual(c.stdout[0], "000102030405060708090a0b0c0d0e0f")
        except:
            c.quiet = False
            print(c)
            raise
        print("O_RAW_NL")

    def test_AP_rawExtreme(self) -> None:
        c: Command = Command(self.AP_RAW_EXTREME, raw=True)

        Job.Run(c, self.RUN_MS)

        try:
            self.assertEqual(len(c.stdout), 1)
            self.assertEqual(len(c.stderr), 0)
            self.assertEqual(c.exitCode, 0)
            self.assertEqual(c.stdout[0], "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f505152535455565758595a5b5c5d5e5f606162636465666768696a6b6c6d6e6f707172737475767778797a7b7c7d7e7f808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9fa0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebfc0c1c2c3c4c5c6c7c8c9cacbcccdcecfd0d1d2d3d4d5d6d7d8d9dadbdcdddedfe0e1e2e3e4e5e6e7e8e9eaebecedeeeff0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
        except:
            c.quiet = False
            print(c)
            raise
        print("P_RAW_ALL")

    def test_AQ_rawAllFail(self) -> None:
        c: Command = Command(self.AP_RAW_EXTREME, raw=False)

        Job.Run(c, self.RUN_MS)

        try:
            self.assertEqual(len(c.stdout), 1)
            self.assertEqual(len(c.stderr), 0)
            self.assertEqual(c.exitCode, 0)
            self.assertEqual(c.stdout[0], "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f505152535455565758595a5b5c5d5e5f606162636465666768696a6b6c6d6e6f707172737475767778797a7b7c7d7e7f808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9fa0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebfc0c1c2c3c4c5c6c7c8c9cacbcccdcecfd0d1d2d3d4d5d6d7d8d9dadbdcdddedfe0e1e2e3e4e5e6e7e8e9eaebecedeeeff0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
        except:
            c.quiet = False
            print(c)
            raise
        print("Q_RAW_ALLFAIL")

    def test_AR_rawAllFail(self) -> None:
        c: Command = Command(self.AR_RAW_ALLERR, raw=False)

        Job.Run(c, self.RUN_MS)

        try:
            self.assertEqual(len(c.stdout), 0)
            self.assertEqual(len(c.stderr), 1)
            self.assertEqual(c.exitCode, 0)
            self.assertEqual(c.stderr[0], "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f505152535455565758595a5b5c5d5e5f606162636465666768696a6b6c6d6e6f707172737475767778797a7b7c7d7e7f808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9fa0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebfc0c1c2c3c4c5c6c7c8c9cacbcccdcecfd0d1d2d3d4d5d6d7d8d9dadbdcdddedfe0e1e2e3e4e5e6e7e8e9eaebecedeeeff0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
        except:
            c.quiet = False
            print(c)
            raise
        print("R_RAW_ALLERR")

    def test_AS_env(self) -> None:
        """
        Secrets go through env: readable by the process, never part of str(Command)
        """
        c: Command = Command("printenv UT_SECRET", env={"UT_SECRET": "b32fea58"})
        Job.Run(c, self.RUN_MS)

        self.assertEqual(c.stdout, ["b32fea58"])
        shown: dict = json.loads(str(c))
        shown["stdout"] = []        # the output of the command itself is of course what it printed
        self.assertNotIn("b32fea58", json.dumps(shown))
        self.assertIn("\n  ", str(c))   # indent=2
        print("S_ENV")

    def test_AT_quote(self) -> None:
        """
        Command.quote() keeps spaces and single quotes of a path intact
        """
        c: Command = Command("echo " + Command.quote("it's a test"))
        Job.Run(c, self.RUN_MS)

        self.assertEqual(c.stdout, ["it's a test"])
        print("T_QUOTE")

    def test_AU_stdin(self) -> None:
        """stdin: the bytes arrive, an empty input is an input too, no stdin is /dev/null (no hang on a terminal)"""
        c: Command = Job.Run(Command("cat", stdin=b"hello\nworld\n"))
        self.assertEqual((c.exitCode, c.stdout, c.stderr), (0, ["hello", "world"], []))

        c = Job.Run(Command("cat", stdin=b""))
        self.assertEqual((c.exitCode, c.stdout, c.killed), (0, [], False))

        beg: float = time()
        c = Job.Run(Command("cat"))             # would wait for the terminal, if stdin was inherited
        self.assertEqual((c.exitCode, c.stdout, c.killed), (0, [], False))
        self.assertLess(time() - beg, 1)
        print("U_STDIN")

    def test_AV_stdin_binary(self) -> None:
        """Every byte value goes in and comes out unchanged (raw)"""
        data: bytes = bytes(range(256)) * 4
        c: Command = Job.Run(Command("cat", raw=True, stdin=data), self.RUN_MS)
        self.assertEqual(c.exitCode, 0)
        self.assertEqual(bytes.fromhex(c.stdout[0]), data)
        print("V_STDIN_BINARY")

    def test_AW_stdin_big(self) -> None:
        """Input and output far bigger than the pipe buffers (64 KiB) must not block each other"""
        data: bytes = os.urandom(4 * 1024 * 1024)
        c: Command = Job.Run(Command("cat", raw=True, stdin=data), self.RUN_MS)
        self.assertEqual((c.exitCode, c.killed), (0, False))
        self.assertEqual(bytes.fromhex(c.stdout[0]), data)

        c = Job.Run(Command("wc -c", stdin=data), self.RUN_MS)      # reads all, writes a little
        self.assertEqual(c.stdout, [str(len(data))])
        print("W_STDIN_BIG")

    def test_AX_stdin_unread(self) -> None:
        """A process that never reads its input: the writer ends quietly, the exit code tells the truth"""
        c: Command = Job.Run(Command("true", stdin=b"x" * 1024 * 1024), self.RUN_MS)
        self.assertEqual((c.exitCode, c.killed, c.status_msg), (0, False, []))
        c = Job.Run(Command("false", stdin=b"x" * 1024 * 1024), self.RUN_MS)
        self.assertEqual((c.exitCode, c.killed), (1, False))
        print("X_STDIN_UNREAD")

    def test_AY_stdin_deadline(self) -> None:
        """A killed Command with a big input leaves no stuck writer behind"""
        c: Command = Command(self.AJ_WAITTIME, stdin=b"x" * 4 * 1024 * 1024)
        beg: float = time()
        Job.Run(c, deadlineMs=500)
        self.assertLess(time() - beg, 1.5)
        self.assertTrue(c.killed)
        c.cleanup()
        self.assertTrue(all(not t.is_alive() for t in c.readers))
        print("Y_STDIN_DEADLINE")

    def test_AZ_stdin_is_secret(self) -> None:
        """The input may hold keys: only its size is shown, and it is released once the process has it"""
        secret: bytes = b"SECRET-KEY-0123456789"
        c: Command = Command("cat", stdin=secret)
        self.assertEqual(c.stdinSize, len(secret))
        Job.Run(c)
        self.assertEqual(c.stdout, ["SECRET-KEY-0123456789"])       # the answer is the caller's business
        self.assertIsNone(c.stdin)
        self.assertNotIn("SECRET-KEY", str(c.process.args))
        self.assertEqual(c._asdict()["stdin_bytes"], len(secret))
        self.assertNotIn("SECRET", str(c._asdict()["cmd"]) + json.dumps({k: v for k, v in c._asdict().items() if k not in {"stdout"}}))
        self.assertEqual(Command("cat")._asdict()["stdin_bytes"], -1)
        print("Z_STDIN_SECRET")


if __name__ == '__main__':
    unittest.main()
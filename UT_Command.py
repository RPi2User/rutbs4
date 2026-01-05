import unittest
from time import sleep, time

# Module imports
from backend.Command import Command


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
    AJ_WAITTIME: str = "sleep 10"
    AK_KILL: str = "ping localhost"
    AL_HEXOUT: str = "dd if=/dev/urandom bs=512 count=1 2>/dev/null"
    AN_CLEANUP: str = "echo 0"
    AN_CLEANUP1: str = "echo the quick brown fox jumps over the lazy dog"

    """_summary_
    Depdencies:
    - your favorite flavour of LINUX
    - pwd
    - ping
    - dd
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
        print("A")

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

        print("B")

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
        print("C")

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
            - c.wait()
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

        print("D")

    def test_AE_Wait(self) -> None:
        """
        Does the same as AD but instead of the while loop it uses c.wait()
        """

        c: Command = Command(self.AE_WAIT)
        self.assertEqual(c.cmd, self.AE_WAIT)
        c.wait()

        # Exit validation
        self.assertNotEqual(c.pid, 0)
        self.assertEqual(c.running, False)
        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.didRun, True)
        self.assertEqual(c.closed, True)

        print("E")

    def test_AF_STDOUT(self) -> None:
        """
        Test if command successfully writes test UUID to STDOUT
        """

        c: Command = Command(self.AF_STDOUT)
        self.assertEqual(c.cmd, self.AF_STDOUT)
        c.wait()

        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.stdout[0], "b32fea58-45ec-4276-a129-ee4f1ee441ae")
        self.assertEqual(c.stderr, [])
        print("F")

    def test_AG_STDERR(self) -> None:
        """
        Test if command successfully writes test UUID to STDERR
        """

        c: Command = Command(self.AG_STDERR)
        self.assertEqual(c.cmd, self.AG_STDERR)
        c.wait()

        self.assertEqual(c.exitCode, 0)
        self.assertEqual(c.stdout, [])
        self.assertEqual(c.stderr[0], "b32fea58-45ec-4276-a129-ee4f1ee441ae")
        print("G")

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
        c.wait()

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

        print("H")

    def test_AI_IO_256(self) -> None:
        """
        Test IO of 256 MiB File Transfer with 50 MByte of tolerance
        """
        c: Command = Command(self.AI_DD256MIB)
        self.assertEqual(c.cmd, self.AI_DD256MIB)
        c.wait()

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

        print("I")

    def test_AJ_WaitTimeout(self) -> None:
        """
        This test does terminate cmd mid-way with the c.wait(timeout=xxx) (xxx in 10ms)
        Default Value 100 -> 1sec / 1000ms
        """

        c: Command = Command(self.AJ_WAITTIME)
        self.assertEqual(c.cmd, self.AJ_WAITTIME)

        beg_time = time()
        c.wait(100)
        end_time = time()

        try:
            self.assertLess((end_time - beg_time), 1.5)   # sleep 10, timeout of 1sec -> should be max 1500ms (rounding errors)
            self.assertEqual(len(c.status_msg), 1)
            self.assertEqual(c.status_msg[0], "Timeout reached, process killed")
            self.assertNotEqual(c.exitCode, 0)
        except AssertionError:
            c.quiet = False
            print(c)
            raise

        print("J")

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

        print("K")

    def test_AL_HEXOUT(self) -> None:
        """
        Tests if command supports hex output properly
        """

        c: Command = Command(self.AL_HEXOUT, raw=True)
        c.wait()

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

        print("L")

    def test_AM_HEXERR(self) -> None:
        """
        Same as AL_HEXOUT but now looking if exception Handling is done properly
        - c.status_msg must contain a error Message
        """

        c: Command = Command(self.AL_HEXOUT)
        c.wait()

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

        print("M")

    def test_AN_cleanup(self) -> None:
        # This tests Command.reset() clears stdout
        c: Command = Command(self.AN_CLEANUP)
        c.wait()
        try:
            self.assertEqual(c.stdout[0], "0")
            c.reset()
            c.cmd = self.AN_CLEANUP1
            c.wait()
            self.assertNotEqual(c.stdout[0], "0")

        except AssertionError:
            c.quiet = False
            print(c)
            raise

        print("N")

if __name__ == '__main__':
    unittest.main()
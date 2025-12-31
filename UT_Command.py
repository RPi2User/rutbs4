import unittest
from time import sleep

# Module imports
from backend.Command import Command


class UT_Command(unittest.TestCase):

    AA_CREATE: str = ""
    AB_VAL: str = ""
    AC_START: str = "cd"
    AD_BACK: str = "ping localhost -c 2"

    """_summary_
    Depdencies:
    - your favorite flavour of LINUX
    - cd
    - ping
    """

    def test_AA_create(self):
        """
        Creates a Command object and tests:
            - c is a Object of "Command"
            - c.toString() will raise an Exception
            - c is cleaned successfully
        """
        c: Command = Command(self.AA_CREATE)    # Calls constructor
        print("[CREATE] " + str(c)) # Tests c.toString()

        self.assertEqual(type(c), Command)
        self.assertEqual(c.closed, True)
        print("A")                  # Prompt User

    def test_AB_validation(self):
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
        This will test if the "cd" command works on the machine.
            - cd shall complete instant
            - for un-godly slow Systems a 100ms sleep is included but always not needed
            - my premise is that the command is finished after c.start().status() get called
            - this does not test concurrency!
        Test flow:
            1. create c with "cd"
            2. start c
            3. sleep 100ms (for very slow systems)
            4. refresh all states from c
            5. Check Params:
                - c.cmd == "cd"
                - c.pid != 0
                - c.exitCode == 0
            6. cleanup

        Why "cd"? Name a OS (that supports Python) were cd is NOT available! I wait for your merge request...
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

        Does NOT test:
            - valid stdout/stderr
            - c.wait() (Done in AE)
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
        self.assertEqual(c.didRan, True)
        self.assertNotEqual(c.stdout, [])
        self.assertEqual(c.stderr, [])
        self.assertEqual(c.exitCode, 0)



        c.cleanup()


if __name__ == '__main__':
    unittest.main()
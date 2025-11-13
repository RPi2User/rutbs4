from backend.Command import Command
from backend.Folder import Folder
from backend.Tape import Tape
from backend.TapeDrive import TapeDrive
from backend.TableOfContent import TableOfContent, TOC_System

class Debugger():

    def main():
        # Lets create a toc :3

        # 1. lets create a drive :3
        drive: TapeDrive = TapeDrive("/dev/null", "", True, "200K")
        drive.ejectCommand = Command("echo eject")
        drive.rewindCommand = Command("echo rewind")

        # 2. Insert a virtual tape :D
        drive.tape = Tape("a810")

        # 3. Construct needed objects ^^
        rootFolder: Folder = Folder("/opt/rutbs/test")
        system: TOC_System = TOC_System(drive, 4)

        # FIRE
        toc: TableOfContent = TableOfContent(rootFolder, system)

        print(toc)

from typing import List
from backend.Folder import Folder
from backend.Command import Command

class Debugger():

    def main():
        subdirs: List[Folder] = []
        f: Folder = Folder("/opt/rutbs/test")
        c: Command = Command("find '" + f.path + "' -mindepth 1 -maxdepth 1 -type d")

        c.wait()

        for q in c.stdout:
            subdirs.append(Folder(q))

        print(subdirs)

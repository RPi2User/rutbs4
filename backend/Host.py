from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid
import json
import os
import time
import subprocess
import re
import socket
import psutil

from backend.Response import Response

from backend.Mount import Mount
from tbk.TDv2 import TapeDrive
from tbk.TableOfContent import TableOfContent
from tbk.File import File

DEBUG: bool = False
VERSION: str = "4.0.0"

class Host():
    
    uuid: str
    response: Response = Response(response='', mimetype="text/plain", status=0)
    hostname : str
    ip_addr: str
    uptime: int
    CPUbyCore: dict
    mem : dict
    load : tuple
    drives : list[TapeDrive] = list[TapeDrive]()
    threadCount: int
    threadLimit: int = 0
    
    mounts : list[Mount]

    """_summary_
    This handles the Main Logic.

    Theory of Operation:
       - Each API Request gets fetched here
       - each Public Method returns self.response  
    """
    
    def __init__(self):
        self.uuid = str(uuid.uuid4())
        self.refresh_status()

    def __str__(self) -> str:
        self.refresh_status()
        data = {
            "hostname": self.hostname,
            "host-uuid": self.uuid,
            "last_response": self.response._asdict(),
            "ip_addr": self.ip_addr,
            "uptime": self.uptime,
            "CPUbyCore": self.CPUbyCore,
            "threadCount": self.threadCount,
            "threadLimit": self.threadLimit,
            "mem": self.mem,
            "load": self.load,
            "tape_drives": self.drives
        }

        return json.dumps(data, indent=2)

    def greeter(self) -> Response:
        self.response = Response(
                            response="THIS IS A RUTBS BACKEND!",
                            mimetype="text/plain",
                            status=200
                        )
        return self.response

    def setThreadlimit(self, count: int) -> Response:
        _response_text: str = "ERROR setting ThreadLimit failed! See Logs"
        _status_code = 500

        if (count <= self.threadLimit):
            self.threadLimit = count
            _response_text = "ThreadLimit set: " + str(self.threadLimit) + " of " + str(self.threadCount)
            _status_code = 200
        else:
            _response_text = "ThreadLimit higher then ThreadCount! Currently: " + str(self.threadLimit) + " of " + str(self.threadCount)
            _status_code = 400

        self.response = Response(
            response= _response_text,
            mimetype="text/plain",
            status=_status_code
        )
        return self.response


    def status(self) -> Response:
        self.refresh_status()
        _drives = {}
        for drive in self.drives:
            _drives.update({drive.path : drive._asdict()}) 
        data = {
            "hostname": self.hostname,
            "host-uuid": self.uuid,
            "last_response": self.response._asdict(),
            "ip_addr": self.ip_addr,
            "uptime": self.uptime,
            "CPUbyCore": self.CPUbyCore,
            "threadCount": self.threadCount,
            "threadLimit": self.threadLimit,
            "mem": self.mem,
            "load": self.load,
            "tape_drives": _drives
        }

        
        # This one does NOT use self.response because message len
        # will rise recursively. We do not like recursion!
        return Response(
                response=json.dumps(data),
                mimetype="application/json",
                status=200)


    def DEBUG(self) -> Response:
        _response_text: str = ""
        _response_mimetype: str = "text/plain"
        _response_code = 400

        if DEBUG:
            # THIS is the Entry Point!
            pass
        else:
            _response_text = "No Bugs found"
            _response_mimetype = "text/plain"
            _response_code = 418

        self.response = Response(
            response=_response_text,
            mimetype=_response_mimetype,
            status=_response_code)
        return self.response

    def Version(self) -> Response:
        data = {
            "version": VERSION
        }
        self.response = Response(
            response=json.dumps(data),
            mimetype="application/json",
            status=200
        )

        return self.response
        
    # This keeps track of ALL system variables, maybe a "isInit: bool" will be added
    def refresh_status(self):
        self.hostname = socket.gethostname()
        try:
            self.ip_addr = socket.gethostbyname(self.hostname)
        except socket.gaierror:
            self.ip_addr = "127.0.0.1"
        
        self.uptime = (int) (time.time() - psutil.boot_time())
        self.CPUbyCore = psutil.cpu_percent(percpu=True)
        self.threadCount = len(self.CPUbyCore)

        if (self.threadLimit == 0):     # if ThreadLimit not initialized, then set it to max.
            self.threadLimit = self.threadCount

        self.mem = psutil.virtual_memory()._asdict()
        self.load = psutil.getloadavg() if hasattr(psutil, "getloadavg") else "N/A"

        self.get_drives(silent=True)
    
    def get_drives(self, silent: bool = False) -> Response:
        _response_text: str
        _response_mime: str
        _response_code: int

        # TODO migrate result to backend.Command() to achive 
        result = subprocess.run(["find", "/dev", "-maxdepth", "1", "-type", "c"], capture_output=True, text=True)
        drive_map = {}

        for dev in result.stdout.split("\n"):
            dev = dev.strip().split("/")[-1] 
            match = re.match(r"^(nst|st)(\d+)$", dev)
            if match:
                drive_type, drive_id = match.groups()
                full_path = f"/dev/{dev}"

                if drive_id not in drive_map:
                    drive_map[drive_id] = {
                        "id": drive_id,
                        "alias": f"st{drive_id}",
                        "path": None,
                        "alt_path": None
                    }

                if drive_type == "st":
                    drive_map[drive_id]["path"] = full_path
                else:
                    drive_map[drive_id]["alt_path"] = full_path

        for i in range(len(drive_map.values())):
            current_element: dict = drive_map.get(str(i)) 
            tape_drive: TapeDrive = TapeDrive(
                alias = current_element["alias"],
                path_to_tape_drive=current_element["path"]
            )
            self.drives.append(tape_drive)

        if silent:
            return self.response

        if (len(self.drives) == 0):
            _response_code = 204
            _response_mime = "text/plain"
            _response_text = "No tape drive found."
        else:
            _response_code = 200
            _response_mime = "application/json"
            data = {}
            for drive in self.drives:
                data.update({drive.path : drive._asdict()})
            _response_text = json.dumps(data)
        self.response = Response(
            response=_response_text,
            mimetype=_response_mime,
            status=_response_code
        )
        return self.response

    # Gets JSON from a single drive
    # 200: Drive found
    # 404: No drive Found
    # 500: Everything else, like st0 is on fire
    def get_tape_drive(self, alias) -> Response:

        _response_text: str
        _response_mime: str
        _response_code: int = 0
        try:
            _drive: TapeDrive
            for drive in self.drives:
                if (drive.alias == alias):
                    _drive = drive
                    break

            
            _response_text=json.dumps(_drive._asdict())
            _response_mime="application/json"
            _response_code=200

        except KeyError:
            _response_code=404
            _response_mime="text/plain"
            _response_text=""

        except Exception as e:
            _response_code=500
            _response_mime="text/plain"
            _response_text="Unkown Exception: \r\n" + str(e)

        self.response = Response(
            response=_response_text,
            status=_response_code,
            mimetype=_response_mime
        )

        return self.response

    def get_mounts(self):
        result = subprocess.run(
            ["df", "-x", "tmpfs", "-x", "devtmpfs", "-x", "efivarfs", "--output=source,size,used,target,fstype"],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.strip().split("\n")[1:]  # Skip header, sadly "df" does not have a "--quiet | --no-head" option
        mounts : list[Mount] = []
        
        for line in lines:
            parts = line.split()
            if len(parts) == 5:
                mounts.append(Mount(
                    filesystem=parts[0],
                    size=int(parts[1]),
                    used=int(parts[2]),
                    mountpoint=parts[3],
                    fstype=parts[4]
                ))
                
        return json.dumps({"mounts": [mount.__dict__ for mount in mounts]})
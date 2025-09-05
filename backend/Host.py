from concurrent.futures import ThreadPoolExecutor, as_completed
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

class Host():
    
    response: Response(response="", mimetype="text/plain", status=200)
    hostname : str
    ip_addr: str
    uptime: int
    CPUbyCore: dict
    mem : dict
    load : tuple
    tape_drives : dict
    threadLimit: int
    
    mounts : list[Mount]

    """_summary_
    This handles the Main Logic.

    Theory of Operation:
       - Each API Request gets fetched here
       - each Public Method returns self.response  
    """
    
    def __init__(self):
        self.refresh_status()
        self.tape_drives = {}
        for drive in self.get_drives()["tape_drives"]:
            alias = drive["alias"]
            alt_path = drive["alt_path"]
            self.tape_drives[alias] = TapeDrive(alt_path)
    
    def __str__(self) -> str:
        self.refresh_status()
        data = {
            "hostname": self.hostname,
            "last_response": self.response,
            "ip_addr": self.ip_addr,
            "uptime": self.uptime,
            "threadLimit": self.threadLimdit,
            "CPUbyCore": self.CPUbyCore,
            "mem": self.mem,
            "load": self.load,
            "tape_drives": self.tape_drives
        }
        return json.dumps(data, indent=2)

    def greeter(self) -> str:
        return "THIS IS A RUTBS BACKEND"

    def DEBUG(self) -> str:
        # This is the Main Debug Entry Point
        pass
        
    def refresh_status(self):
        self.hostname = socket.gethostname(),
        #self.ip_addr = socket.gethostbyname(self.hostname)
        self.uptime = (int) (time.time() - psutil.boot_time())
        self.CPUbyCore = psutil.cpu_percent(percpu=True)
        self.mem = psutil.virtual_memory()._asdict()
        self.load = psutil.getloadavg() if hasattr(psutil, "getloadavg") else "N/A"
    
    def get_drives(self) -> json:
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

        drives = [drive for drive in drive_map.values() if drive["path"]]
        return {"tape_drives": drives}
    
    def get_tape_drive(self, alias) -> TapeDrive:
        try:
            return self.tape_drives.get(alias)
        except:
            return None

    
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
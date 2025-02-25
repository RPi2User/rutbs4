import json
import os
import subprocess
import re
import socket
import psutil

class Host():
    def __init__(self):
        pass

    def get_host_status():
        status = {
            "Servername": socket.gethostname(),
            "IP-Adresse": socket.gethostbyname(socket.gethostname()),
            "CPUusageByCore": psutil.cpu_percent(percpu=True),
            "RAM": psutil.virtual_memory()._asdict(),
            "Load": psutil.getloadavg() if hasattr(psutil, "getloadavg") else "N/A"
        }
        return json.dumps(status), 200, {'Content-Type': 'application/json'}
    
    def get_drives():
        tape_drives = []
        pattern = re.compile(r'^(nst\d+|st\d+)$')  # Regex für "nstX" oder "stX"

        if os.name == "posix":
            dev_dir = "/dev"
            for device in os.listdir(dev_dir):
                if pattern.match(device):
                    tape_drives.append(os.path.join(dev_dir, device))

        return json.dumps({"tape_drives": tape_drives}), 200, {'Content-Type': 'application/json'}
    
    def get_mounts():
        result = subprocess.run(
            ["df", "-x", "tmpfs", "-x", "devtmpfs", "-x", "efivarfs", "--output=source,size,used,target,fstype"],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.strip().split("\n")[1:]  # Erste Zeile (Header) überspringen
        mounts = []
        
        for line in lines:
            parts = line.split()
            if len(parts) == 5:
                mounts.append({
                    "filesystem": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "mountpoint": parts[3],
                    "fstype": parts[4]
                })
        
        return json.dumps({"mounts": mounts})
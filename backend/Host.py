import json
import os
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
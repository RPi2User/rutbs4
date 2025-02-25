import json
import os
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
        
        # Prüft unter Linux nach Gerätenamen mit "st" oder "nst" (typische Bandlaufwerke)
        if os.name == "posix":
            dev_dir = "/dev"
            for device in os.listdir(dev_dir):
                if "st" in device or "nst" in device:
                    tape_drives.append(os.path.join(dev_dir, device))
        
        return json.dumps({"tape_drives": tape_drives}), 200, {'Content-Type': 'application/json'}
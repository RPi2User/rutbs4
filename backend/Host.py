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

        # Entferne unvollständige Einträge
        drives = [drive for drive in drive_map.values() if drive["path"]]

        return json.dumps({"tape_drives": drives})
    
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
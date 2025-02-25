import json
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
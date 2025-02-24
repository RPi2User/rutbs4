import requests
import os
from tbk.File import File
from tbk.TableOfContent import TableOfContent
from tbk.TapeDrive import TapeDrive

VERSION: str = "4.0"
DEBUG: bool = True

class Server:
    def __init__(self, hostname: str, ip: str, port: int = 5533):
        self.hostname = hostname
        self.ip = ip
        self.port = port
        self.version = None

    def get_version(self):
        url = f'http://{self.ip}:{self.port}/version'
        response = requests.get(url)
        if response.status_code == 200:
            self.version = response.json()
            print(f"{self.hostname} Version: {self.version}")
        else:
            print(f"Fehler beim Abrufen der Version von {self.hostname} Statuscode {response.status_code}")

if __name__ == '__main__':
    server = Server("tape-01", "localhost", 5534)
    server.get_version()
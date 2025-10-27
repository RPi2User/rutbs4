import json

from backend.Command import Command

class Checksum:
    
    MD5: int = 1
    SHA256: int = 2
    
    type: int = MD5
    file_path: str = ""

    cmd: Command = Command("")

    def create(self):

        if (self.type == self.MD5):
            self.cmd = Command("openssl md5 '" + self.file_path +"'")

        else:
            pass

    def __init__(self, file_path: str, type: int = MD5):
        self.type = type
        self.file_path = file_path
        
    def _asdict(self) -> dict:
        data = {
            "type" : self.type,
            "value" : self.value,
            "command": self.cmd._asdict()
        }
        return data

    def __str__(self):
        return json.dumps(self._asdict())
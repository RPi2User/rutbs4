class Checksum:
    
    type: str
    value: str

    def __init__(self, value: str = "00000000000000000000000000000000", type: str = "md5"):
        self.type = type
        self.value = value
        
    def _asdict(self) -> dict:
        data = {
            "type" : self.type,
            "value" : self.value
        }
        return data

    def __str__(self):
        return f"{self.type}, {self.value}"
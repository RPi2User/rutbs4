class checksum:
    
    type: str
    value: str

    def __init__(self, value: str, type: str = "md5"):
        self.type = type
        self.value = value

    def __str__(self):
        return f"{self.type}: {self.value}"
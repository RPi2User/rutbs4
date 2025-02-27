class File:

    id: int
    size : int
    name : str
    path : str
    cksum : str
    cksum_type : str
    

    def __init__(self, id: int, size: int, name: str, path: str, cksum: str = "", cksum_type: str = "") -> None:
        self.id: int = id
        self.size: int = size
        self.name: str = name
        self.path: str = path
        self.cksum: str = cksum
        self.cksum_type: str = cksum_type
    
    def __str__(self) -> str:
        return "File(ID: " + str(self.id) + ", Size: " + str(self.size) + ", Name: " + self.name + ", Path: " + self.path + ", cksum: " + self.cksum + ", cksum_type: " + self.cksum_type + ")\n"
    
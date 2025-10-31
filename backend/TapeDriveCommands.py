from backend.Command import Command


class TapeDriveCommands:
    
    # COMMAND ENUM
    REWIND = 1
    EJECT = 2
    
    
    path: str = "<undefined>"
    generic_path: str = "<undefined>"
    
    def __init__(self):
        pass
    
    

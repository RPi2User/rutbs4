from backend.Command import Command


class TapeDriveCommands:
    
    # COMMAND ENUM
    REWIND = 1
    EJECT = 2
    
    
    path: str = "<undefined>"
    generic_path: str = "<undefined>"
    
    def __init__(self):
        pass
    
    
    COMMANDS = {
        REWIND : Command("sg_raw '" + generic_path + "' 0x01 0 0 0 0 0"),
        EJECT : Command("sg_raw '" + generic_path + "' 0x1B 0 0 0 0 0"),
    }
from backend.Command import Command


class TapeDrive:
    
    # ACTION ENUM
    REWIND = 1
    EJECT = 2
    
    
    path: str = "<undefined>"
    FOO: int = 400
    
    
    COMMANDS = {
        REWIND : Command("mt -f " + path + " rewind"),
        EJECT : Command("mt -f " + path + " eject"),
    }
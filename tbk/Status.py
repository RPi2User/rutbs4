from enum import Enum

class Status(Enum):
    ERROR = 0
    NO_TAPE = 1
    TAPE_RDY = 2
    TAPE_RDY_WP = 3
    NOT_AT_BOT = 4
    WRITING = 5
    READING = 6
    EJECTING = 7
    REWINDING = 8
    NOT_IMPLEMENTED = 255
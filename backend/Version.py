class Version:

    """
    #### === VERSION ==========================================================

    The backend version, kept in one place. It fits into 16 bit:

        0bMMMM mmmm bbbb bbbb
          |    |    └ bugfix (0-255)
          |    └ minor (0-15)
          └ major (0-15)

        4.0.0 -> 0x4000

    | `Version.`           | Description                                  |
    |----------------------|----------------------------------------------|
    | `Version.text()`     | "4.0.0"                                      |
    | `Version.word()`     | 16 bit value, stored on tape / in the chip   |
    | `Version.fromWord()` | 16 bit value -> "4.0.0"                      |
    """

    MAJOR: int = 4
    MINOR: int = 0
    BUGFIX: int = 0

    @staticmethod
    def text() -> str:
        return f"{Version.MAJOR}.{Version.MINOR}.{Version.BUGFIX}"

    @staticmethod
    def word() -> int:
        return (Version.MAJOR << 12) | (Version.MINOR << 8) | Version.BUGFIX

    @staticmethod
    def fromWord(word: int) -> str:
        return f"{(word >> 12) & 0xF}.{(word >> 8) & 0xF}.{word & 0xFF}"

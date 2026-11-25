import json
import os
import platform
import uuid

from typing import List
from datetime import datetime
from enum import Enum

from backend.Command import Command
from backend.Encryption import Encryption, E_Mode
from backend.Job import Job
from backend.TapeDrive import TapeDrive
from backend.Folder import Folder
from backend.Version import Version

"""_summary_
    Host must create a suitable TOC, with a valid TapeDrive object.
    After that, the TOC must be passed to the Read/Write-Scheduler
"""

class TOC_State(Enum):
    IDLE = 0        # first TOC: the plan, nothing finished (no write is running while it is sealed)
    COMPLETE = 1    # trailing TOC: everything is on the tape
    FAILED = 2      # trailing TOC of an aborted job

class TOC_WrongPassphrase(Exception):
    pass

class TOC_Header:

    """
    Clear text part of the TOC. Anybody holding the tape can read it, so it must never
    contain key material: the drive is reduced to vendor / model / serial on purpose
    (TapeDrive._asdict() would carry the file the drive is working on).
    """

    FORMAT: str = "rutbs"

    def __init__(self, tapeDrive: TapeDrive, threadCount: int, fingerprint: str = "",
                 bodyCipher: E_Mode = E_Mode.AES256CTR):
        self.version: int = Version.word()
        self.fingerprint: str = fingerprint or str(uuid.uuid4())
        self.state: TOC_State = TOC_State.IDLE
        self.timeStamp = datetime.now().isoformat(timespec="seconds")
        self.hostname = platform.node()
        self.threadCount = threadCount
        self.blocksize: str = tapeDrive.blocksize
        self.bodyCipher: E_Mode = bodyCipher
        self.drive: dict = {
            "vendor": tapeDrive.vendor,
            "model": tapeDrive.model,
            "serial": tapeDrive.serial,
        }
        self.tape: dict = {
            "lto-version": tapeDrive.tape.lto_version.name,
            "native_capacity": tapeDrive.tape.native_capacity,
        }

    def _asdict(self)-> dict:
        data = {
            "format": self.FORMAT,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "state": self.state.name,
            "created": self.timeStamp,
            "hostname": self.hostname,
            "threadCount": self.threadCount,
            "blocksize": self.blocksize,
            "drive": self.drive,
            "tape": self.tape,
            "body_cipher": self.bodyCipher.name,
        }
        return data

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)


class TableOfContent:

    CIPHER_DEADLINE_MS: int = 60000     # the whole TOC goes through openssl, it can be big

    """_summary_
        A TableOfContent is stored as one JSON document:

            {"header": {...clear text...}, "body": "<base64 of the encrypted body>"}

        The header names the tape (fingerprint), the state and the cipher of the body.
        The body holds the folders with all their files, including the key and IV of every
        file, and is encrypted with the passphrase of the tape. A wrong passphrase shows as
        a body that is not valid JSON.

        After `removeEncryption()` the TOC is plain: `body_cipher` is NONE, the body is the JSON
        object itself, the files have no key, and no passphrase is needed to seal or open it.
        Anybody holding the tape can then read the file names, paths and checksums.

        | `TableOfContent.`           | Description                                          |
        |-----------------------------|------------------------------------------------------|
        | `removeEncryption()`        | Makes the TOC and all its files plain, before the first `seal()` |
        | `seal(passphrase)`          | Returns the JSON document, remembers it in `sealed`  |
        | `store(directory)`          | Writes `sealed` to YYYYMMDD_hhmmss_<fingerprint>.json |
        | `TableOfContent.readHeader(text)` | Header only, no passphrase needed              |
        | `TableOfContent.open(text, passphrase="")` | Header and body as dicts              |
        | `TableOfContent.differences(first, last)` | What the plan of the first and the last TOC disagrees on |

        The first TOC is sealed with state IDLE when the checksums are known and before the first file
        is written, the trailing one with state COMPLETE or FAILED after everything ran. Apart from
        the state and the command log they are equivalent.
    """


    def __init__(self, folder: Folder, header: TOC_Header) -> None:
        self.folder: Folder = folder    # all files below the input directory, in tape order
        self.header: TOC_Header = header
        self.sealed: str = ""

    def removeEncryption(self) -> None:
        """
        The unencrypted request: the body cipher and the encryption of every file become NONE,
        the keys are dropped. Has to run before the job is queued (the queue decides which phases
        a file needs) and before the first seal().
        """
        if self.sealed:
            raise RuntimeError("The TOC is sealed already") # NOTE Only API will call this function, only if context is right
        self.header.bodyCipher = E_Mode.NONE
        self.folder.removeEncryption()

    def _body(self) -> dict:
        return {"folder": self.folder._asdict()}

    def _asdict(self) -> dict:
        """Everything in clear text, keys included. For tests and debugging only, never for the tape."""
        return {"header": self.header._asdict(), **self._body()}

    def __str__(self) -> str:
        return json.dumps(self._asdict(), indent=2)

    # CIPHER
    # The passphrase goes to openssl through the environment, the plain body through stdin:
    # neither shows up in `ps` and no plain text file is left behind.
    @staticmethod
    def _openssl(mode: E_Mode, decrypt: bool, passphrase: str, data: bytes) -> bytes:
        cmd: str = (Encryption.MODE_CMD[mode] + ("-d" if decrypt else "-e") +
                    " -a -A -pass env:" + Encryption.KEY_ENV)
        # raw: the answer comes back as hex, so any bytes survive
        result: Command = Job.Run(Command(cmd, raw=True, env={Encryption.KEY_ENV: passphrase}, stdin=data),
                                  TableOfContent.CIPHER_DEADLINE_MS)
        if result.exitCode != 0:
            why: str = bytes.fromhex(result.stderr[0]).decode(errors="replace") if result.stderr else ""    # raw: hex
            raise TOC_WrongPassphrase("openssl failed: " + " ".join(result.status_msg + [why]).strip())
        return bytes.fromhex(result.stdout[0]) if result.stdout else b""

    # WRITE
    def seal(self, passphrase: str = "") -> str:
        if self.header.bodyCipher is E_Mode.NONE:
            if passphrase:
                raise ValueError("A plain TOC takes no passphrase")
            self.sealed = json.dumps({"header": self.header._asdict(), "body": self._body()}, indent=2)
            return self.sealed

        if not passphrase:
            raise ValueError("A passphrase is required to seal the TOC")

        body: bytes = json.dumps(self._body()).encode()
        encrypted: bytes = self._openssl(self.header.bodyCipher, False, passphrase, body)

        self.sealed = json.dumps({"header": self.header._asdict(), "body": encrypted.decode()}, indent=2)
        return self.sealed

    def store(self, directory: str) -> str:
        """Keeps a copy of the sealed TOC in the TOC directory and returns its path."""
        if not self.sealed:
            raise ValueError("seal() the TOC before storing it")

        stamp: str = datetime.fromisoformat(self.header.timeStamp).strftime("%Y%m%d_%H%M%S")
        path: str = os.path.join(directory, stamp + "_" + self.header.fingerprint + ".json")
        with open(path, "w") as f:
            f.write(self.sealed)
        return path

    # READ
    @staticmethod
    def readHeader(text: str) -> dict:
        document: dict = json.loads(text)
        if document.get("header", {}).get("format") != TOC_Header.FORMAT:
            raise ValueError("Not a rutbs TOC")
        return document["header"]

    @staticmethod
    def open(text: str, passphrase: str = "") -> dict:
        """
        Returns {"header": {...}, "body": {...}}. Raises TOC_WrongPassphrase if the body cannot be read.
        A plain TOC (body_cipher NONE) needs no passphrase, a given one is ignored.
        """
        header: dict = TableOfContent.readHeader(text)
        mode: E_Mode = E_Mode[header["body_cipher"]]
        if mode is E_Mode.NONE:
            return {"header": header, "body": json.loads(text)["body"]}
        try:
            plain: bytes = TableOfContent._openssl(mode, True, passphrase, json.loads(text)["body"].encode())
            return {"header": header, "body": json.loads(plain)}
        except (TOC_WrongPassphrase, ValueError) as e:  # json.JSONDecodeError and UnicodeDecodeError are ValueErrors
            raise TOC_WrongPassphrase("Wrong passphrase or damaged TOC") from e

    @staticmethod
    def differences(first: dict, last: dict) -> List[str]:
        """
        Compares two opened TOCs (the first and the last one of a tape). Both must describe the same
        plan: the same tape, the same folder and, for every file, the same id, paths, size, cipher,
        key, IV and checksum (type and value; the write job knows every checksum before the first
        TOC is written). What may differ is the result: the state of the header, the state and the
        commands of the files.
        Returns what differs, an empty list means "the same tape, the same files".
        """
        out: List[str] = []

        for key in sorted(set(first["header"]) | set(last["header"])):
            if key != "state" and first["header"].get(key) != last["header"].get(key):
                out.append("header." + key + ": " + str(first["header"].get(key)) + " <> " + str(last["header"].get(key)))

        a: dict = first["body"]["folder"]
        b: dict = last["body"]["folder"]
        for key in ("path", "encryption_type"):
            if a.get(key) != b.get(key):
                out.append("folder." + key + ": " + str(a.get(key)) + " <> " + str(b.get(key)))
        if len(a["files"]) != len(b["files"]):
            out.append("folder has " + str(len(a["files"])) + " files in the first and " + str(len(b["files"])) + " in the last TOC")
            return out

        for x, y in zip(a["files"], b["files"]):
            name: str = "file " + str(x["id"]) + ": "
            fields: dict = {
                "id": (x["id"], y["id"]),
                "size": (x["size"], y["size"]),
                "path": (x["path"], y["path"]),
                "cksum.type": (x["cksum"]["type"], y["cksum"]["type"]),
                "encryption.mode": (x["encryption"]["mode"], y["encryption"]["mode"]),
                "key": (x["encryption"]["key"]["value"], y["encryption"]["key"]["value"]),
                "iv": (x["encryption"]["key"]["iv"], y["encryption"]["key"]["iv"]),
            }
            for field, (left, right) in fields.items():
                if left != right:
                    out.append(name + field + " differs")
            if x["cksum"]["value"] != y["cksum"]["value"]:
                out.append(name + "cksum.value differs")

        return out

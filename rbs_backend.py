import argparse
import json
import os
import time
from flask import Flask, request
from flasgger import Swagger # type: ignore

from tbk.File import File
from tbk.TableOfContent import TableOfContent

from tbk.TDv2 import TapeDrive

from backend.Host import Host
from tbk.Status import Status

VERSION = 4
DEBUG = True

host: Host = Host()
tapeDrive: TapeDrive = None # Host need to provide a TapeDrive with Host.getTapeDrive(alias)

app = Flask(__name__)
swagger = Swagger(app)

# -----------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def get_slash():
    """
    Root endpoint
    ---
    tags:
      - General
    responses:
      200:
        description: Returns a simple HTML response
    """
    return app.response_class(response="<html><body>THIS IS A RUTBS-BACKEND</body></html>", 
                              mimetype='application/html')


@app.route('/host', methods=['GET'])
def get_host():
    """
    Get host information
    ---
    tags:
      - Host
    responses:
      200:
        description: Host is reachable
    """
    return '', 200

@app.route('/host/debug', methods=['GET'])  # Quick and easy Debugging-Entry-Point
def get_host_debug():
    """
    Debugging endpoint, only available if DEBUG is True
    ---
    tags:
      - Host
    responses:
      418:
        description: Debugging completed
    """
    if DEBUG:
        
        tapeDrive = host.get_tape_drive("st0")
        current_toc: TableOfContent = tapeDrive.readTOC()
        for file in current_toc.files:
            file.path = "/opt/read_test/" + file.name
        host.calcChecksums(current_toc)

        # for file in current_toc.files:
        #     file.path = "/tmp/readtest" # Changed! user-defined destiation "entrypoint"
        #     tapeDrive.read(file)
        print("DEBUG Done")
        
    return tapeDrive.getStatusJson(), 418

@app.route('/host/version', methods=['GET'])
def get_host_version():
    """
    Get backend version
    ---
    tags:
      - Host
    responses:
      200:
        description: Returns the backend version in JSON format
    """
    return app.response_class(response=json.dumps({"version": VERSION}), 
                              mimetype='application/json')

@app.route('/host/status', methods=['GET'])
def get_host_status():
    """
    Get host status
    ---
    tags:
      - Host
    responses:
      200:
        description: Returns the host status
    """
    return host.get_host_status()

@app.route('/host/drives', methods=['GET'])
def get_host_drives():
    """
    Get all drives of Host
    ---
    tags:
      - Host
    responses:
      200:
        description: Returns a list of all drives
    """
    return host.get_drives()

@app.route('/host/mounts', methods=['GET'])
def get_host_mounts():
    """
    Get all mounts of Host
    ---
    tags:
      - Host
    responses:
      200:
        description: Returns a list of all mounts
    """
    return host.get_mounts()

# -BASIC-DRIVE-OPERATIONS------------------------------------------------------

@app.route('/drive/', methods=['GET'])  # Get all drives
def get_drive_root():
    """
    Get all drives managed by this backend
    ---
    tags:
      - Drive Operations
    responses:
      200:
        description: Returns a list of all drives
      204:
        description: No drives found
    """
    drives = host.get_drives()
    if drives != None :
        return drives, 200
    return '', 204

@app.route('/drive/<alias>', methods=['GET'])  # Get .toString() of a specific drive
def get_drive(alias):
    """
    Get details of a specific drive
    ---
    tags:
      - Drive Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
    responses:
      200:
        description: Returns details of the specified drive
      404:
        description: Drive not found
    """
    tapeDrive = host.get_tape_drive(alias)
    if tapeDrive != None:
        return str(tapeDrive), 200
    return '', 404

@app.route('/drive/<alias>/status', methods=['GET']) # Get status of a specific drive
def get_drive_status(alias):
    """
    Get status of a specific drive
    ---
    tags:
      - Drive Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
    responses:
      200:
        description: Returns the status of the specified drive
      404:
        description: Drive not found
    """
    tape_drive = host.get_tape_drive(alias)
    if tape_drive:
        return tape_drive.getStatusJson(), 200
    return '', 404


@app.route('/drive/<alias>/eject', methods=['POST']) # Eject a specific drive
def post_drive_eject(alias):
    """
    Eject a specific drive
    ---
    tags:
      - Drive Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
    responses:
      200:
        description: Drive ejected successfully
      404:
        description: Drive not found
    """
    tape_drive = host.get_tape_drive(alias)
    if tape_drive:
        tape_drive.eject()
        return '', 200
    return '', 404

@app.route('/drive/<alias>/rewind', methods=['POST']) # Rewind a specific drive
def post_drive_rewind(alias):
    """
    Rewind a specific drive
    ---
    tags:
      - Drive Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
    responses:
      200:
        description: Drive rewound successfully
      404:
        description: Drive not found
    """
    tape_drive = host.get_tape_drive(alias)
    if tape_drive:
        tape_drive.rewind()
        return '', 200
    return '', 404

@app.route('/drive/<alias>/abort', methods=['POST']) # Abort current drive operation
def post_drive_abort(alias):
    """
    Abort current drive operation
    ---
    tags:
      - Drive Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
    responses:
      200:
        description: Operation aborted successfully
      500:
        description: Error during job abort, restart application immediately
    """
    tape_drive = host.get_tape_drive(alias)
    if tape_drive:
        tape_drive.cancelOperation()
        return 'Success, Remount Tape and clean your Filestorage! ', 200
    return '[ERROR] DURING JOB ABORT, RESTART APPLICATION IMMEDIATELY!', 500

@app.route('/drive/<alias>/read', methods=['POST'])  # Start read process for a specific drive
def post_drive_read(alias):
    """
    Start read process for a specific drive
    ---
    tags:
      - Drive Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            destPath:
              type: string
              description: Destination path for the read files
            checksumming:
              type: string
              description: Enable or disable checksumming ("true" or "false")
            ejectAfterSuccess:
              type: string
              description: Whether to eject the tape after a successful read ("true" or "false")
    responses:
      200:
        description: Read completed successfully
      400:
        description: Bad request (missing destPath, checksumming, or ejectAfterSuccess)
      404:
        description: Drive not found
      409:
        description: Tape not ready, remount required
      500:
        description: Checksum mismatch or other error
    """
    tape_drive = host.get_tape_drive(alias)
    if not tape_drive:
        return 'Drive not found', 404
    
    if tape_drive.getStatus() not in {Status.TAPE_RDY.value, Status.TAPE_RDY_WP.value, Status.NOT_AT_BOT.value}:
        # Check if the tape exists
        status_json = tape_drive.getStatusJson()
        status_json["recommended_action"] = "Remount Tape!"
        return status_json, 409
    
    # Extract the destination path and other fields from the request JSON
    request_data = request.get_json()
    if not request_data or 'destPath' not in request_data or 'checksumming' not in request_data or 'ejectAfterSuccess' not in request_data:
        return 'Bad Request: "destPath", "checksumming", and "ejectAfterSuccess" are required in the request body', 400

    # Parse JSON Data
    
    dest_path = request_data['destPath']
    checksumming = request_data['checksumming']
    eject_after_success = request_data['ejectAfterSuccess'].lower() == 'true'
    tape_drive.checksumming = checksumming.lower() != 'false'
    
    # Get fresh TOC
    toc: TableOfContent = tape_drive.readTOC()
    if toc is None:
        return '[READ] Failed, TOC not readable', 500
    # READ entire Tape
    toc = tape_drive.readTape(toc, dest_path)
    
    # Check whether the read was successful
    if toc is None:
        return tape_drive.getStatusJson(), 500

    # Eject the tape if requested
    if eject_after_success:
        tape_drive.eject()
        
        while tape_drive.getStatus() == Status.EJECTING.value:
            time.sleep(0.1)

    return '[READ] Completed', 200

@app.route('/drive/<alias>/write', methods=['POST'])  # Start write process for a specific drive
def post_drive_write(alias):
    """
    Start write process for a specific drive
    ---
    tags:
      - Drive Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            create:
              type: object
              properties:
                dir:
                  type: string
                  description: Directory to scan for files
                bs:
                  type: string
                  description: Block size for the operation
                ltoV:
                  type: integer
                  description: LTO version of the tape
            system:
              type: object
              properties:
                cksum:
                  type: string
                  description: Whether to calculate checksums ("true" or "false")
                ejectAfterSuccess:
                  type: string
                  description: Whether to eject the tape after a successful write ("true" or "false")
    responses:
      200:
        description: Write operation completed successfully
      400:
        description: Bad request (missing or invalid parameters)
      404:
        description: Drive not found
    """
    # Get the tape drive
    tape_drive = host.get_tape_drive(alias)
    if not tape_drive:
        return '[ERROR] Drive not found', 404

    # Parse the request data
    request_data = request.get_json()
    if not request_data or 'create' not in request_data or 'system' not in request_data:
        return '[ERROR] Bad Request: "create" and "system" are required in the request body', 400

    create_data = request_data['create']
    system_data = request_data['system']
    required_create_fields = ['dir', 'bs', 'ltoV']
    required_system_fields = ['cksum', 'ejectAfterSuccess']

    if not all(field in create_data for field in required_create_fields):
        return '[ERROR] Bad Request: Missing required fields in "create"', 400
    if not all(field in system_data for field in required_system_fields):
        return '[ERROR] Bad Request: Missing required fields in "system"', 400

    # Create the TOC
    toc: TableOfContent = TableOfContent([], "", "", 0, "")
    toc = toc.create(
        target_dir=create_data['dir'],
        blocksize=create_data['bs'],
        ltoVersion=create_data['ltoV'],
        cksum=system_data['cksum'].lower() == 'true'
    )
    if toc is None:
        return '[ERROR] Failed to create TOC', 500

    statuscode: int = tape_drive.writeTape(toc, eject=system_data['ejectAfterSuccess'].lower() == 'true')

    return tape_drive.getStatusJson(), statuscode

# -TOC-REQS--------------------------------------------------------------------

@app.route('/drive/<alias>/toc/read', methods=['GET'])
def get_drive_toc_read(alias):
    """
    Read the Table of Content (TOC) from a specific drive
    ---
    tags:
      - TOC Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
    responses:
      200:
        description: Returns the TOC as JSON
      409:
        description: Tape not ready, rewind required
      500:
        description: TOC not readable, remount required
    """
    tape_drive = host.get_tape_drive(alias)
    if tape_drive.getStatus() in {Status.TAPE_RDY.value, Status.TAPE_RDY_WP.value, Status.NOT_AT_BOT.value}:
        _toc = tape_drive.readTOC()  # This returns None-Type when the TOC is not readable
        if type(_toc) is TableOfContent:
            return _toc.getAsJson(), 200
        else:
            status_json = tape_drive.getStatusJson()
            status_json["recommended_action"] = "Remount tape!"
            return status_json, 500
    else:
        status_json = tape_drive.getStatusJson()
        status_json["recommended_action"] = "Rewind tape and try again!"
        return status_json, 409
@app.route('/drive/<alias>/toc/create', methods=['POST'])
def post_drive_toc_create(alias):
    """
    Create a Table of Content (TOC) Object for <drive>
    ---
    tags:
      - TOC Operations
    parameters:
      - name: alias
        in: path
        type: string
        required: true
        description: Alias of the tape drive
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            create:
              type: object
              properties:
                dir:
                  type: string
                  description: Directory to scan for files
                bs:
                  type: string
                  description: Block size for the operation
                ltoV:
                  type: integer
                  description: LTO version of the tape
            system:
              type: object
              properties:
                cksum:
                  type: string
                  description: Whether to calculate checksums ("true" or "false")
    responses:
      200:
        description: Returns the created TOC as JSON
      400:
        description: Bad request (missing or invalid parameters)
      404:
        description: Drive not found
    """
    # Get the tape drive
    tape_drive = host.get_tape_drive(alias)
    if not tape_drive:
        return '[ERROR] Drive not found', 404

    # Parse the request data
    request_data = request.get_json()
    if not request_data or 'create' not in request_data or 'system' not in request_data:
        return '[ERROR] Bad Request: "create" and "system" are required in the request body', 400

    create_data = request_data['create']
    system_data = request_data['system']
    required_create_fields = ['dir', 'bs', 'ltoV']
    required_system_fields = ['cksum']

    if not all(field in create_data for field in required_create_fields):
        return '[ERROR] Bad Request: Missing required fields in "create"', 400
    if not all(field in system_data for field in required_system_fields):
        return '[ERROR] Bad Request: Missing required fields in "system"', 400

    # Create the TOC
    toc: TableOfContent = TableOfContent([], "", "", 0, "")
    toc = toc.create(
        target_dir=create_data['dir'],
        blocksize=create_data['bs'],
        ltoVersion=create_data['ltoV'],
        cksum=system_data['cksum'].lower() == 'true'
    )
    if toc is None:
        return '[ERROR] Failed to create TOC', 500

    return toc.getAsJson(), 200

# THIS ONE WILL LEAVE. At this stage there is no reason to implement a Path
# that just writes a TOC. A tape should be written as a whole!
# There are no implementations to fast forward or rewind the tape.
@app.route('/drive/<alias>/toc/write', methods=['POST'])
def get_drive_toc_write(alias):
    # BACKEND SHOULD GENERATE TOC not USER!
    tape_drive = host.get_tape_drive(alias)
    if not tape_drive:
        return '[ERROR] Drive not found', 404

    # Extract the TOC from the request JSON
    request_data = request.get_json()
    if not request_data or 'toc' not in request_data:              # Added extra field for system_data
        return '[ERROR] Bad Request: "toc" is required in the request body', 400    

    toc = TableOfContent([], "", "", 0, "")
    if toc.from_json(request_data['toc']):
        # Placeholder for writing TOC to the tape drive
        # tape_drive.writeTOC(toc)  # Uncomment when implemented
        if DEBUG: print(str(toc))
        return 'Success!', 200
    else:
        return '[ERROR] Invalid TOC format', 400

# -MAIN-ENTRYPOINT-------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start RBS Backend Server")
    parser.add_argument('--port', type=int, default=5533, help='Port number')
    args = parser.parse_args()
    
    app.run(host='0.0.0.0', port=args.port)
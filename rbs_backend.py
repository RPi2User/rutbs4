import argparse
import json
from flask import Flask

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

# -----------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def get_slash():
    return app.response_class(response="<html>THIS IS A RUTBS-BACKEND</html>", 
                              mimetype='application/html')


@app.route('/host', methods=['GET'])
def get_host():
    return '', 200

@app.route('/host/debug', methods=['GET'])  # Quick and easy Debugging-Entry-Point
def get_host_debug():
    if DEBUG:
        
        f: File = File(0, "Ä$Ö ÜP.tmp", "/tmp")
        tapeDrive = host.get_tape_drive("st0")
        tapeDrive.read(f)
        
    return tapeDrive.getStatusJson(), 418

@app.route('/host/version', methods=['GET'])
def get_host_version():
    return app.response_class(response=json.dumps({"version": VERSION}), 
                              mimetype='application/json')

@app.route('/host/status', methods=['GET'])
def get_host_status():
    return host.get_host_status()

@app.route('/host/drives', methods=['GET'])
def get_host_drives():
    return host.get_drives()

@app.route('/host/mounts', methods=['GET'])
def get_host_mounts():
    return host.get_mounts()

# -BASIC-DRIVE-OPERATIONS------------------------------------------------------

@app.route('/drive/', methods=['GET'])  # Get all drives
def get_drive_root():
    drives = host.get_drives()
    if drives != None :
        return drives, 200
    return '', 204

@app.route('/drive/<alias>', methods=['GET'])  # Get .toString() of a specific drive
def get_drive(alias):
    tapeDrive = host.get_tape_drive(alias)
    if tapeDrive != None:
        return str(tapeDrive), 200
    return '', 404

@app.route('/drive/<alias>/status', methods=['GET']) # Get status of a specific drive
def get_drive_status(alias):
    tape_drive = host.get_tape_drive(alias)
    if tape_drive:
        return tape_drive.getStatusJson(), 200
    return '', 404


@app.route('/drive/<alias>/eject', methods=['POST']) # Eject a specific drive
def post_drive_eject(alias):
    tape_drive = host.get_tape_drive(alias)
    if tape_drive:
        tape_drive.eject()
        return '', 200
    return '', 404

@app.route('/drive/<alias>/rewind', methods=['POST']) # Rewind a specific drive
def post_drive_rewind(alias):
    tape_drive = host.get_tape_drive(alias)
    if tape_drive:
        tape_drive.rewind()
        return '', 200
    return '', 404

@app.route('/drive/<alias>/abort', methods=['POST']) # Abort current drive operation
def post_drive_abort(alias):
    tape_drive = host.get_tape_drive(alias)
    if tape_drive:
        tape_drive.cancelOperation()
        return '', 200
    return '[ERROR] DURING JOB ABORT, RESTART APPLICATION IMMEDIATELY!', 500

# -TOC-REQS--------------------------------------------------------------------


@app.route('/drive/<alias>/toc/read', methods=['GET'])
def get_drive_toc(alias):
    tape_drive = host.get_tape_drive(alias)
    if tape_drive.status in {Status.TAPE_RDY.value, Status.TAPE_RDY_WP.value}:
        _toc: TableOfContent = tape_drive.readTOC()
        return app.response_class(response=tape_drive.toc2xml(_toc), mimetype='application/xml')
    else:
        status_json = tape_drive.getStatusJson()
        status_json["recommended_action"] = "Rewind tape and try again!"
        return status_json, 409
    


# -MAIN-ENTRYPOINT-------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start RBS Backend Server")
    parser.add_argument('--port', type=int, default=5533, help='Port number')
    args = parser.parse_args()
    
    app.run(host='0.0.0.0', port=args.port)
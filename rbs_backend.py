import argparse
import json
from flask import Flask

from tbk.File import File
from tbk.TableOfContent import TableOfContent
from tbk.TapeDrive import TapeDrive

from tbk.TDv2 import TapeDrive as TD2

from backend.Host import Host

VERSION = 4
DEBUG = True

host: Host = Host()

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
        f: File = File(0, "toc.tmp", "/tmp")
        td: TD2 = TD2("/dev/nst0")
        td.read(f)
    return '', 418

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

# -----------------------------------------------------------------------------

@app.route('/drive/', methods=['GET'])
def get_drive_root():
    drives = host.get_drives()
    if drives != None :
        return drives, 200
    return '', 204
    

@app.route('/drive/<alias>', methods=['GET'])
def get_drive(alias):
    drives = host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            return drive, 200
    return '', 404

@app.route('/drive/<alias>/status', methods=['GET'])
def get_drive_status(alias):
    drives = host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            drive_altPath: str = drive["alt_path"]
            tapeDrive: TD2 = TD2(drive_altPath)
            return app.response_class(response=json.dumps(
                {"status": str(tapeDrive.getStatus())}),
                mimetype='application/json')
    return '', 404

@app.route('/drive/<alias>/toc/read', methods=['GET'])
def get_drive_toc(alias):
    drives = host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            drive_altPath: str = drive["alt_path"]
            tapeDrive: TD2 = TD2(drive_altPath)
            return app.response_class(response=tapeDrive.readTOC(), 
                                      mimetype='application/xml')
        
    return '', 404

@app.route('/drive/<alias>/eject', methods=['POST'])
def post_drive_eject(alias):
    drives = host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            drive_altPath: str = drive["alt_path"]
            tapeDrive: TD2 = TD2(drive_altPath)
            tapeDrive.eject()
            return '', 200         
    return '', 404

@app.route('/drive/<alias>/rewind', methods=['POST'])
def post_drive_rewind(alias):
    drives = host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            drive_altPath: str = drive["alt_path"]
            tapeDrive: TD2 = TD2(drive_altPath)
            tapeDrive.rewind()
            return '', 200         
    return '', 404

# -----------------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start RBS Backend Server")
    parser.add_argument('--port', type=int, default=5533, help='Port number')
    args = parser.parse_args()
    
    app.run(host='0.0.0.0', port=args.port)
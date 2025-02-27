import argparse
import json
from flask import Flask

from tbk.File import File
from tbk.TableOfContent import TableOfContent
from tbk.TapeDrive import TapeDrive

from tbk.TDv2 import TapeDrive as TD2

from backend.Host import Host

VERSION = 4

app = Flask(__name__)

# -----------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def get_slash():
    return app.response_class(response="<html>THIS IS A RUTBS-BACKEND</html>", 
                              mimetype='application/html')


@app.route('/host', methods=['GET'])
def get_host():
    return '', 200

@app.route('/host/version', methods=['GET'])
def get_host_version():
    return app.response_class(response=json.dumps({"version": VERSION}), 
                              mimetype='application/json')

@app.route('/host/status', methods=['GET'])
def get_host_status():
    return Host.get_host_status()

@app.route('/host/drives', methods=['GET'])
def get_host_drives():
    return Host.get_drives()

@app.route('/host/mounts', methods=['GET'])
def get_host_mounts():
    return Host.get_mounts()

# -----------------------------------------------------------------------------

@app.route('/drive/', methods=['GET'])
def get_drive_root():
    drives = Host.get_drives()
    if drives != None :
        return drives, 200
    return '', 400
    

@app.route('/drive/<alias>', methods=['GET'])
def get_drive(alias):
    drives = Host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            return drive, 200
    return '', 400

@app.route('/drive/<alias>/status', methods=['GET'])
def get_drive_status(alias):
    drives = Host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            drive_altPath: str = drive["alt_path"]
            tapeDrive: TD2 = TD2(drive_altPath)
            return app.response_class(response=json.dumps(
                {"status": str(tapeDrive.getStatus())}),
                mimetype='application/json')
    return '', 400

@app.route('/drive/<alias>/toc', methods=['GET'])
def get_drive_toc(alias):
    drives = Host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            drive_altPath: str = drive["alt_path"]
            tapeDrive: TapeDrive = TapeDrive(drive_altPath)
            return app.response_class(response=tapeDrive.readTOC(), 
                                      mimetype='application/xml')
        
    return '', 400

@app.route('/drive/<alias>/eject', methods=['POST'])
def post_drive_eject(alias):
    drives = Host.get_drives()
    for drive in drives["tape_drives"]:
        drive_alias : str = drive["alias"]
        if drive_alias == alias:
            drive_altPath: str = drive["alt_path"]
            tapeDrive: TapeDrive = TapeDrive(drive_altPath)
            tapeDrive.eject()
            return '', 200         
    return '', 400
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start RBS Backend Server")
    parser.add_argument('--port', type=int, default=5533, help='Port number')
    args = parser.parse_args()
    
    app.run(host='0.0.0.0', port=args.port)
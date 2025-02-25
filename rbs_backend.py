import argparse
import json
from flask import Flask

from tbk.File import File
from tbk.TableOfContent import TableOfContent
from tbk.TapeDrive import TapeDrive

from backend.Host import Host

VERSION = 4

app = Flask(__name__)

@app.route('/host/version', methods=['GET'])
def get_host_version():
    return app.response_class(response=json.dumps({"version": VERSION}), mimetype='application/json')

@app.route('/host/status', methods=['GET'])
def get_host_status():
    return Host.get_host_status()

@app.route('/host/drives', methods=['GET'])
def get_host_drives():
    return Host.get_drives()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start RBS Backend Server")
    parser.add_argument('--port', type=int, default=5533, help='Port number')
    args = parser.parse_args()
    
    app.run(host='0.0.0.0', port=args.port)
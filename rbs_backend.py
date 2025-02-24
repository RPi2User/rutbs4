import argparse
import json
from flask import Flask

from tbk.File import File
from tbk.TableOfContent import TableOfContent
from tbk.TapeDrive import TapeDrive

VERSION = 4

app = Flask(__name__)

@app.route('/version', methods=['GET'])
def get_version():
    return app.response_class(response=json.dumps({"version": VERSION}), mimetype='application/json')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start RBS Backend Server")
    parser.add_argument('--port', type=int, default=5533, help='Port number')
    args = parser.parse_args()
    
    app.run(host='0.0.0.0', port=args.port)
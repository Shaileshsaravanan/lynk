import os
import json
import subprocess
import sys
import base64
import requests
import signal
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

current_app_info = {}

def load_time_data():
    with open("data/time.json", "r") as f:
        return json.load(f)
    
def image_url_to_base64(image_url):
    response = requests.get(image_url)
    print(f"Image URL: {image_url}")
    print(f"Response status code: {response.status_code}")
    if response.status_code == 200:
        image_data = response.content
        print(f"Image data length: {len(image_data)}")
        return base64.b64encode(image_data).decode('utf-8')
    else:
        print(f"Failed to fetch image from URL. Status code: {response.status_code}")
        raise Exception(f"Failed to fetch image from URL. Status code: {response.status_code}")


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tracking', methods=['GET', 'POST'])
def tracking():
    apps_json_path = 'data/apps.json'

    if request.method == 'GET':
        if not os.path.isfile(apps_json_path):
            return render_template('tracking.html', apps_data={})
        
        with open(apps_json_path, 'r') as f:
            apps_data = json.load(f)
        
        return render_template('tracking.html', apps_data=apps_data)

    elif request.method == 'POST':
        if not request.json:
            return jsonify({"error": "No JSON data received"}), 400

        updated_apps_data = request.json

        if not isinstance(updated_apps_data, dict):
            return jsonify({"error": "Invalid data format"}), 400
        
        with open(apps_json_path, 'w') as f:
            json.dump(updated_apps_data, f, indent=4)
        
        return jsonify({"message": "apps.json updated successfully"}), 200

    return render_template('tracking.html')

@app.route('/api/hello')
def hello():
    return jsonify({"message": "Hello from Flask!"})

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/connection')
def connection():
    return render_template('connection.html')

@app.route('/storage')
def storage():
    return render_template('storage.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/api/update-app', methods=['POST'])
def api_update_alias():
    if not request.json:
        return jsonify({"error": "No JSON data received"}), 400

    app_name = request.json.get('app_name')
    new_alias = request.json.get('alias')
    icon_url = request.json.get('icon_url')

    if not app_name or not isinstance(new_alias, str):
        return jsonify({"error": "Invalid input"}), 400

    apps_json_path = 'data/apps.json'
    if not os.path.isfile(apps_json_path):
        return jsonify({"error": "apps.json not found"}), 404

    with open(apps_json_path, 'r') as f:
        apps_data = json.load(f)

    if app_name not in apps_data:
        return jsonify({"error": f"App '{app_name}' not found"}), 404
    print('icon',icon_url)

    if icon_url:
        try:
            icon_base64 = image_url_to_base64(icon_url)
            print(f"Icon base64: {icon_base64}")
        except Exception as e:
            return jsonify({"error": f"Error converting image URL to base64: {str(e)}"}), 500
        apps_data[app_name]['icon'] = icon_base64
        apps_data[app_name]['icon_url'] = icon_url

    apps_data[app_name]['alias'] = new_alias

    with open(apps_json_path, 'w') as f:
        json.dump(apps_data, f, indent=4)

    return jsonify({"message": "success"}), 200

def start_tracking():
    global track_process
    track_process = subprocess.Popen([sys.executable, 'track.py'])
    print(f"Started track.py with PID: {track_process.pid}")

def stop_tracking():
    if track_process:
        print(f"Stopping track.py with PID: {track_process.pid}")
        os.kill(track_process.pid, signal.SIGTERM)

if __name__ == '__main__':
    start_tracking()
    import atexit
    atexit.register(stop_tracking)
    app.run(debug=True, host='localhost', port=5001)
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import threading
import pywinctl as pwc
import psutil
import platform
import time
import json
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def get_active_app_name():
    window = pwc.getActiveWindow()
    if not window:
        return None
    if platform.system() == "Windows":
        pid = window.getPID()
        return psutil.Process(pid).name().removesuffix(".exe")
    elif platform.system() == "Darwin":
        app_name = window.getParent()
        return app_name[1]
    return None

def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours}h {minutes}m {seconds}s"

def track_active_apps():
    json_path = 'data/time.json'
    apps_json_path = 'data/apps.json'
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    os.makedirs(os.path.dirname(apps_json_path), exist_ok=True)

    if not os.path.isfile(apps_json_path):
        with open(apps_json_path, 'w') as f:
            json.dump({}, f)

    if not os.path.isfile(json_path):
        with open(json_path, 'w') as f:
            json.dump({}, f)

    current_app = None
    current_app_start_time = time.time()

    while True:
        with open(json_path, 'r+') as time_file, open(apps_json_path, 'r+') as apps_file:
            data = json.load(time_file)
            apps_data = json.load(apps_file)

            app_name = get_active_app_name()

            if app_name != current_app and app_name is not None:
                if app_name not in apps_data:
                    apps_data[app_name] = {
                        "alias": app_name,
                        "icon": None,
                        "tracking": 'True'
                    }
                    apps_file.seek(0)
                    json.dump(apps_data, apps_file, indent=4)
                    apps_file.truncate()

                if apps_data.get(app_name, {}).get("tracking", "true") != "true":
                    current_app = app_name
                    current_app_start_time = time.time()
                    continue

                if current_app is not None:
                    duration = time.time() - current_app_start_time
                    formatted_duration = format_duration(duration)
                    current_date = time.strftime("%d-%m-%Y")
                    if current_date not in data:
                        data[current_date] = {}
                    if current_app not in data[current_date]:
                        data[current_date][current_app] = "0h 0m 0s"
                    existing_time = data[current_date].get(current_app, "0h 0m 0s")
                    existing_seconds = convert_time_to_seconds(existing_time)
                    total_seconds = existing_seconds + convert_time_to_seconds(formatted_duration)
                    data[current_date][current_app] = format_duration(total_seconds)
                    time_file.seek(0)
                    json.dump(data, time_file, indent=4)
                    time_file.truncate()

                    socketio.emit('app_switch', {
                        "app": app_name,
                        "usage": data[current_date]
                    })

                current_app = app_name
                current_app_start_time = time.time()

        time.sleep(1)

def convert_time_to_seconds(time_str):
    parts = time_str.split()
    hours = int(parts[0].replace('h', '')) if 'h' in parts[0] else 0
    minutes = int(parts[1].replace('m', '')) if 'm' in parts[1] else 0
    seconds = int(parts[2].replace('s', '')) if 's' in parts[2] else 0
    return hours * 3600 + minutes * 60 + seconds

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tracking')
def tracking():
    return render_template('tracking.html')

@app.route('/api/hello')
def hello():
    return jsonify({"message": "Hello from Flask!"})

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    tracker_thread = threading.Thread(target=track_active_apps, daemon=True)
    tracker_thread.start()
    socketio.run(app, debug=True, host='0.0.0.0', port=5001)
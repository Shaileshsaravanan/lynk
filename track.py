import os
import sys
import time
import psutil
import platform
import subprocess
import pywinctl as pwc
from flask import Flask
from flask_socketio import SocketIO, emit
import threading
import json
import signal
import socket

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

current_pid = os.getpid()
print(f"Current PID: {current_pid}")

for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmdline = proc.info.get('cmdline') or []
        if proc.info['pid'] != current_pid and isinstance(cmdline, list) and 'track.py' in ' '.join(cmdline):
            print(f"Terminating duplicate instance (PID {proc.info['pid']})")
            proc.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

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

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def find_process_using_port(port):
    for proc in psutil.process_iter(['pid', 'name', 'connections']):
        try:
            for conn in proc.connections():
                if conn.laddr.port == port:
                    return proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return None

def stop_existing_server():
    try:
        os.kill(current_pid, signal.SIGTERM)
        for _ in range(5):
            if not is_port_in_use(port=5002):
                break
            time.sleep(1)
    except ProcessLookupError:
        print(f"Process {current_pid} not found")
    except PermissionError:
        print(f"No permission to kill process {current_pid}")

def restart_track_py():
    print("No active window detected, restarting track.py")
    args = [sys.executable] + sys.argv
    subprocess.Popen(args)
    print(f"Exiting current process (PID: {current_pid})")
    os._exit(0)

@app.route('/')
def index():
    return "Track.py SocketIO Server Running"

def track_active_apps():
    current_app = None
    current_app_start_time = time.time()
    json_path = 'data/time.json'
    apps_json_path = 'data/apps.json'
    none_counter = 0
    max_none_count = 5

    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    os.makedirs(os.path.dirname(apps_json_path), exist_ok=True)

    if not os.path.isfile(apps_json_path):
        with open(apps_json_path, 'w') as f:
            json.dump({}, f)

    if not os.path.isfile(json_path):
        with open(json_path, 'w') as f:
            json.dump({}, f)

    while True:
        try:
            with open(json_path, 'r+') as time_file, open(apps_json_path, 'r+') as apps_file:
                data = json.load(time_file)
                apps_data = json.load(apps_file)

                app_name = get_active_app_name()

                if app_name is None:
                    print(f"No active window detected ({none_counter}/{max_none_count})")
                    restart_track_py()

                if app_name != current_app:
                    if app_name not in apps_data:
                        apps_data[app_name] = {"alias": app_name, "icon": None, "icon_url": None, "tracking": 'true'}
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

                        apps_json_path = 'data/apps.json'
                        if not os.path.isfile(apps_json_path):
                            with open(apps_json_path, 'w') as f:
                                json.dump({}, f)
                        with open(apps_json_path, 'r') as apps_file:
                            apps_data = json.load(apps_file)

                        current_app_info = {"app": app_name, "apps_data": apps_data, "usage": data[current_date]}
                        socketio.emit('ping', current_app_info)

                    current_app = app_name
                    current_app_start_time = time.time()

        except Exception as e:
            print(f"Error in track_active_apps: {e}")
            time.sleep(5)

        time.sleep(1)

def convert_time_to_seconds(time_str):
    parts = time_str.split()
    hours = int(parts[0].replace('h', '')) if 'h' in parts[0] else 0
    minutes = int(parts[1].replace('m', '')) if 'm' in parts[1] else 0
    seconds = int(parts[2].replace('s', '')) if 's' in parts[2] else 0
    return hours * 3600 + minutes * 60 + seconds

def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours}h {minutes}m {seconds}s"

def signal_handler(sig, frame):
    print(f"Received signal {sig}, shutting down...")
    os._exit(0)

@socketio.on('connect')
def handle_connect():
    json_path = 'data/time.json'

    if not os.path.isfile(json_path):
        with open(json_path, 'w') as f:
            json.dump({}, f)

    with open(json_path, 'r+') as time_file:
        data = json.load(time_file)
        
        app_name = get_active_app_name()
        current_date = time.strftime("%d-%m-%Y")

        if current_date not in data:
            data[current_date] = {}
        if app_name not in data[current_date]:
            data[current_date][app_name] = "0h 0m 0s"
        
        time_file.seek(0)
        json.dump(data, time_file, indent=4)
        time_file.truncate()
    
    apps_json_path = 'data/apps.json'
    if not os.path.isfile(apps_json_path):
        with open(apps_json_path, 'w') as f:
            json.dump({}, f)
    with open(apps_json_path, 'r') as apps_file:
        apps_data = json.load(apps_file)

    current_app_info = {"app": app_name, "apps_data": apps_data, "usage": data[current_date]}
    socketio.emit('ping', current_app_info)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    tracker_thread = threading.Thread(target=track_active_apps, daemon=True)
    tracker_thread.start()

    print(f"Starting track.py with PID: {current_pid}")
    socketio.run(app, debug=False, use_reloader=False, host='0.0.0.0', port=5002)
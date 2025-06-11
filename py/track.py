import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
packages_path = os.path.join(current_dir, 'python_packages')
sys.path.insert(0, packages_path)

import time
import psutil
import platform
import subprocess
import pywinctl as pwc
import json
import signal
import socket
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from socketio import AsyncServer
from socketio import ASGIApp

# Set up FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    if is_port_in_use(5002):
        pid = find_process_using_port(5002)
        print(f"Port 5002 in use by PID {pid}")
        if pid and pid != current_pid:
            os.kill(pid, signal.SIGTERM)
            await asyncio.sleep(2)

    asyncio.create_task(track_active_apps())
    yield
    print("Shutting down gracefully...")

fastapi_app = FastAPI(lifespan=lifespan)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO setup
sio = AsyncServer(async_mode='asgi', cors_allowed_origins='*', logger=False, engineio_logger=False)
app = ASGIApp(sio, other_asgi_app=fastapi_app)

current_pid = os.getpid()
DATA_DIR = os.environ.get('LYNK_DATA_DIR')

print(f"Current PID: {current_pid}")
print(f"Running under Electron: {bool(os.environ.get('ELECTRON_RUN_AS_NODE'))}")
print(f"Data directory: {DATA_DIR}")


def ensure_data_directory():
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

def get_data_file_path(filename):
    return os.path.join(DATA_DIR, filename)

def get_active_app_name():
    try:
        window = pwc.getActiveWindow()
        if not window:
            return None
        if platform.system() == "Windows":
            pid = window.getPID()
            return psutil.Process(pid).name().removesuffix(".exe")
        elif platform.system() == "Darwin":
            app_name = window.getParent()
            if app_name and len(app_name) > 1:
                return app_name[1]
            return None
        return None
    except Exception:
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
        except Exception:
            pass
    return None

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

def restart_server():
    print("Restarting track.py...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def track_active_apps():
    current_app = None
    current_app_start_time = time.time()
    json_path = get_data_file_path('time.json')
    apps_json_path = get_data_file_path('apps.json')
    none_counter = 0
    max_none_count = 5

    ensure_data_directory()
    for path in [json_path, apps_json_path]:
        if not os.path.isfile(path):
            with open(path, 'w') as f:
                json.dump({}, f)

    while True:
        try:
            with open(json_path, 'r') as time_file:
                data = json.load(time_file)
            with open(apps_json_path, 'r') as apps_file:
                apps_data = json.load(apps_file)

            app_name = get_active_app_name()
            if app_name is None:
                none_counter += 1
                print(f"No active window detected ({none_counter}/{max_none_count})")
                if none_counter >= max_none_count:
                    restart_server()
                    none_counter = 0
                await asyncio.sleep(1)
                continue
            else:
                none_counter = 0

            if app_name != current_app:
                if app_name not in apps_data:
                    apps_data[app_name] = {"alias": app_name, "icon": None, "icon_url": None, "tracking": 'true'}
                    with open(apps_json_path, 'w') as apps_file:
                        json.dump(apps_data, apps_file, indent=4)

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
                    existing_seconds = convert_time_to_seconds(data[current_date][current_app])
                    total_seconds = existing_seconds + convert_time_to_seconds(formatted_duration)
                    data[current_date][current_app] = format_duration(total_seconds)
                    with open(json_path, 'w') as time_file:
                        json.dump(data, time_file, indent=4)

                    print(f"{current_app}: {formatted_duration} (Total: {data[current_date][current_app]})")
                    current_app_info = {"app": app_name, "apps_data": apps_data, "usage": data[current_date]}
                    await sio.emit('ping', current_app_info)

                current_app = app_name
                current_app_start_time = time.time()
        except Exception as e:
            print(f"Error in track_active_apps: {e}")
        await asyncio.sleep(1)

@sio.event
async def connect(sid, environ):
    try:
        json_path = get_data_file_path('time.json')
        ensure_data_directory()
        if not os.path.isfile(json_path):
            with open(json_path, 'w') as f:
                json.dump({}, f)

        with open(json_path, 'r+') as time_file:
            try:
                data = json.load(time_file)
            except json.JSONDecodeError:
                data = {}
                time_file.seek(0)
                json.dump(data, time_file, indent=4)
                time_file.truncate()

            app_name = get_active_app_name()
            current_date = time.strftime("%d-%m-%Y")

            if current_date not in data:
                data[current_date] = {}
            if app_name and app_name not in data[current_date]:
                data[current_date][app_name] = "0h 0m 0s"

            time_file.seek(0)
            json.dump(data, time_file, indent=4)
            time_file.truncate()

        apps_json_path = get_data_file_path('apps.json')
        if not os.path.isfile(apps_json_path):
            with open(apps_json_path, 'w') as f:
                json.dump({}, f)
        try:
            with open(apps_json_path, 'r') as apps_file:
                apps_data = json.load(apps_file)
        except json.JSONDecodeError:
            apps_data = {}

        current_app_info = {"app": app_name, "apps_data": apps_data, "usage": data[current_date]}
        await sio.emit('ping', current_app_info, to=sid)
    except Exception as e:
        print(f"Error in handle_connect: {e}")
        await sio.emit('error', {'message': 'Failed to initialize connection'}, to=sid)

if __name__ == '__main__':
    import uvicorn
    ensure_data_directory()
    uvicorn.run(app, host="127.0.0.1", port=5002, log_level="info")

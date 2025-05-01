import pywinctl as pwc
import psutil
import platform
import time
import json
import os

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

if __name__ == "__main__":
    json_path = 'data/apps.json'
    os.makedirs(os.path.dirname(json_path), exist_ok=True)

    if not os.path.isfile(json_path):
        with open(json_path, 'w') as f:
            json.dump({}, f)

    with open(json_path, 'r+') as file:
        data = json.load(file)

        current_app = None
        start_time = time.time()
        while True:
            app_name = get_active_app_name()
            print(f"Current app: {app_name}")
            if app_name != current_app and app_name is not None:
                if current_app is not None:
                    if app_name not in data:
                        data[app_name] = {
                            "alias": app_name,
                            "icon": None
                        }
                        file.seek(0)
                        json.dump(data, file, indent=4)
                        file.truncate()
                        print(f"App '{app_name}' added to JSON.")
                    duration = time.time() - start_time
                    print(f"{current_app}: {duration:.2f} seconds")
                current_app = app_name
                start_time = time.time()
            time.sleep(1)
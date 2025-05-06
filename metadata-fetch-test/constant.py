import platform
import pywinctl as pwc
import psutil
import os
import sys
import time

def get_active_app_name():
    window = pwc.getActiveWindow()
    if not window:
        return None
    if platform.system() == "Windows":
        try:
            pid = window.getPID()
            return psutil.Process(pid).name().removesuffix(".exe")
        except psutil.NoSuchProcess:
            return None
    elif platform.system() == "Darwin":
        app_name = window.getParent()
        return app_name[1]

while True:
    active_app_name = get_active_app_name()
    if active_app_name is None:
        print("No active window detected. Restarting script...")
        time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    print(active_app_name)
    time.sleep(0.5)
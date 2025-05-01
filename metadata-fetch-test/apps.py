import win32gui
import psutil

def get_running_apps():
    windows = []
    win32gui.EnumWindows(lambda hwnd, param: param.append(hwnd), windows)

    app_names = []
    for hwnd in windows:
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            _, pid = win32gui.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(pid)
                app_names.append(process.name())
            except psutil.NoSuchProcess:
                pass
    
    return list(set(app_names))

if __name__ == "__main__":
    running_apps = get_running_apps()
    print(running_apps)
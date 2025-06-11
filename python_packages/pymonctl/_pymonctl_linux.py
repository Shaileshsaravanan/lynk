#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys

assert sys.platform == "linux"

import math
import os
import subprocess
import threading

from typing import Optional, List, Union, Tuple, NamedTuple

import Xlib.display
import Xlib.X
import Xlib.protocol
import Xlib.xobject
from Xlib.protocol.rq import Struct
from Xlib.xobject.drawable import Window as XWindow
from Xlib.ext import randr

from ._main import BaseMonitor, _pointInBox, _getRelativePosition, getMonitorsData, isWatchdogEnabled, \
                   DisplayMode, ScreenValue, Box, Rect, Point, Size, Position, Orientation
from ewmhlib import defaultEwmhRoot, getProperty, getPropertyValue, getRoots, Props


def _getAllMonitors() -> list[LinuxMonitor]:
    return [LinuxMonitor(monitor.crtcs[0]) for monitor in _XgetMonitors()]


def _getAllMonitorsDict() -> dict[str, ScreenValue]:
    # https://stackoverflow.com/questions/8705814/get-display-count-and-resolution-for-each-display-in-python-without-xrandr
    # https://www.x.org/releases/X11R7.7/doc/libX11/libX11/libX11.html#Obtaining_Information_about_the_Display_Image_Formats_or_Screens
    # https://github.com/alexer/python-xlib/blob/master/examples/xrandr.py
    monitorsDict: dict[str, ScreenValue] = {}
    for monitorData in getMonitorsData():
        display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData
        monitorsDict[monName] = _buildMonitorsDict(display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo)
    return monitorsDict


def _getAllMonitorsDictThread() -> (Tuple[dict[str, ScreenValue],
                                          List[Tuple[Xlib.display.Display, Struct, XWindow, randr.GetScreenResourcesCurrent,
                                                     randr.MonitorInfo, str, int, randr.GetOutputInfo, int, randr.GetCrtcInfo]]]):
    # display connections seem to fail when shared amongst threads and/or queried too quickly in parallel
    monitorsDict: dict[str, ScreenValue] = {}
    monitorsData: List[Tuple[Xlib.display.Display, Struct, XWindow, randr.GetScreenResourcesCurrent,
                             randr.MonitorInfo, str, int, randr.GetOutputInfo, int, randr.GetCrtcInfo]] = []
    for monitorData in _getMonitorsData():
        display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData
        monitorsDict[monName] = _buildMonitorsDict(display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo)
        monitorsData.append((display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo))
    return monitorsDict, monitorsData


def _buildMonitorsDict(display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo) -> ScreenValue:

    is_primary = monitor.primary == 1
    x, y, w, h = monitor.x, monitor.y, monitor.width_in_pixels, monitor.height_in_pixels
    wa: List[int] = getPropertyValue(getProperty(window=root, prop=Props.Root.WORKAREA, display=display),
                                     display=display)
    # Thanks to odknt (https://github.com/odknt) for his HELP!!!
    if isinstance(wa, list) and len(wa) >= 4:
        wx, wy, wr, wb = wa[0], wa[1], wa[2], wa[3]
    else:
        wx, wy, wr, wb = x, y, w, h
    mm_width = monitor.width_in_millimeters or outputInfo.mm_width
    mm_height = monitor.height_in_millimeters or outputInfo.mm_height
    if mm_width != 0 and mm_height != 0:
        dpiX, dpiY = round((w * 25.4) / mm_width), round((h * 25.4) / mm_height)
    else:
        dpiX, dpiY = 0.0, 0.0
    scaleX, scaleY = _scale(monName) or (0.0, 0.0)
    rotValue = int(math.log(crtcInfo.rotation, 2))
    if rotValue in (Orientation.NORMAL, Orientation.LEFT, Orientation.RIGHT, Orientation.INVERTED):
        rot = Orientation(rotValue)
    else:
        rot = rotValue
    freq = 0.0
    for mode in res.modes:
        if crtcInfo.mode == mode.id:
            if mode.h_total != 0 and mode.v_total != 0:
                freq = round(mode.dot_clock / (mode.h_total * mode.v_total), 2)
            break
    depth = screen.root_depth

    return {
        "system_name": monName,
        'id': output,
        'is_primary': is_primary,
        'position': Point(x, y),
        'size': Size(w, h),
        'workarea': Rect(wx, wy, wr, wb),
        'scale': (scaleX, scaleY),
        'dpi': (dpiX, dpiY),
        'orientation': rot,
        'frequency': freq,
        'colordepth': depth
    }


def _getMonitorsCount() -> int:
    return len(_XgetMonitors())


def _findMonitor(x: int, y: int) -> List[LinuxMonitor]:
    monitors = []
    for monitor in _XgetMonitors():
        if _pointInBox(x, y, monitor.x, monitor.y, monitor.width_in_pixels, monitor.height_in_pixels):
            monitors.append(LinuxMonitor(monitor.crtcs[0]))
    return monitors


def _getPrimary() -> LinuxMonitor:
    return LinuxMonitor()


def _arrangeMonitors(arrangement: dict[str, dict[str, Optional[Union[str, int, Position, Point, Size]]]]):

    monitors = _XgetMonitorsDict()
    setAsPrimary = ""
    for monName in arrangement.keys():
        relPos = arrangement[monName]["relativePos"]
        relMon = arrangement[monName].get("relativeTo", "")
        if (monName not in monitors.keys() or
                ((isinstance(relPos, Position) or isinstance(relPos, int)) and
                 ((relMon and relMon not in monitors.keys()) or (not relMon and relPos != Position.PRIMARY)))):
            return
        elif relPos == Position.PRIMARY or relPos == (0, 0) or relPos == Point(0, 0):
            setAsPrimary = monName

    newArrangement: dict[str, dict[str, Union[int, bool]]] = {}
    newPos: dict[str, dict[str, int]] = {}
    xOffset = yOffset = 0

    if setAsPrimary:

        targetMonInfo = monitors[setAsPrimary]["monitor"]
        newArrangement[setAsPrimary] = {
            "setPrimary": True,
            "x": 0,
            "y": 0,
            "w": targetMonInfo.width_in_pixels,
            "h": targetMonInfo.height_in_pixels
        }
        newPos[setAsPrimary] = {"x": 0, "y": 0}
        arrangement.pop(setAsPrimary)

    for monName in arrangement.keys():

        arrInfo = arrangement[monName]
        relativePos: Union[Position, int, Point, Tuple[int, int]] = arrInfo["relativePos"]
        targetMonInfo = monitors[monName]["monitor"]
        setPrimary = not setAsPrimary and targetMonInfo.primary == 1

        if setPrimary:

            x, y = 0, 0

        elif isinstance(relativePos, Position) or isinstance(relativePos, int):

            relativeTo: str = arrInfo["relativeTo"]

            targetMon = {"relativePos": relativePos, "relativeTo": relativeTo,
                         "position": Point(targetMonInfo.x, targetMonInfo.y),
                         "size": Size(targetMonInfo.width_in_pixels, targetMonInfo.height_in_pixels)}

            relMonInfo = monitors[relativeTo]["monitor"]
            if relativeTo in newPos.keys():
                relX, relY = newPos[relativeTo]["x"], newPos[relativeTo]["y"]
            else:
                relX, relY = relMonInfo.x, relMonInfo.y
            relMon = {"position": Point(relX, relY),
                      "size": Size(relMonInfo.width_in_pixels, relMonInfo.height_in_pixels)}

            x, y = _getRelativePosition(targetMon, relMon)

        else:

            x, y = relativePos

        if x < 0:
            xOffset += abs(x)
        if y < 0:
            yOffset += abs(y)
        newPos[monName] = {"x": x, "y": y}

        newArrangement[monName] = {
            "setPrimary": setPrimary,
            "x": x,
            "y": y,
            "w": targetMonInfo.width_in_pixels,
            "h": targetMonInfo.height_in_pixels
        }

    if newArrangement:
        cmd = _buildCommand(newArrangement, xOffset, yOffset)
        _, _ = _runProc(cmd)


def _getMousePos() -> Point:
    """
    Get the current coordinates (x, y) of the mouse pointer on given monitor, in pixels

    :return: Point struct
    """
    mp = defaultEwmhRoot.root.query_pointer()
    return Point(mp.root_x, mp.root_y)


_rotations = ["normal", "left", "inverted", "right"]


class LinuxMonitor(BaseMonitor):

    def __init__(self, handle: Optional[int] = None):
        """
        Class to access all methods and functions to get info and manage monitors plugged to the system.

        This class is not meant to be directly instantiated. Instead, use convenience functions like getAllMonitors(),
        getPrimary() or findMonitor(x, y).

        It can raise ValueError exception in case provided handle is not valid
        """
        monitorData = _XgetMonitorData(handle)
        if monitorData:
            self.display, self.screen, self.root, _, self.handle, self.name = monitorData
        else:
            raise ValueError

    @property
    def size(self) -> Optional[Size]:
        monitors = _XgetMonitors(self.name)
        if monitors:
            monitor = monitors[0]
            return Size(monitor.width_in_pixels, monitor.height_in_pixels)
        return None

    @property
    def workarea(self) -> Optional[Rect]:
        # https://askubuntu.com/questions/1124149/how-to-get-taskbar-size-and-position-with-python
        wa: List[int] = getPropertyValue(
            getProperty(window=self.root, prop=Props.Root.WORKAREA, display=self.display), display=self.display)
        if wa:
            wx, wy, wr, wb = wa[0], wa[1], wa[2], wa[3]
            return Rect(wx, wy, wr, wb)
        return None

    @property
    def position(self) -> Optional[Point]:
        monitors = _XgetMonitors(self.name)
        if monitors:
            monitor = monitors[0]
            return Point(monitor.x, monitor.y)
        return None

    def setPosition(self, relativePos: Union[int, Position, Point, Tuple[int, int]], relativeTo: Optional[str]):
        # https://askubuntu.com/questions/1193940/setting-monitor-scaling-to-200-with-xrandr
        arrangement: dict[str, dict[str, Optional[Union[str, int, Position, Point, Size]]]] = {}
        monitors: dict[str, dict[str, randr.MonitorInfo]] = _XgetMonitorsDict()
        monKeys = list(monitors.keys())
        if relativePos == Position.PRIMARY:
            monitor = monitors[self.name]["monitor"]
            if monitor.primary == 1:
                return
            # For homogeneity, placing PRIMARY at (0, 0) and all the rest to RIGHT_TOP
            try:
                index = monKeys.index(self.name)
                monKeys.pop(index)
            except:
                return
            arrangement[self.name] = {"relativePos": relativePos, "relativeTo": None}
            xOffset = monitor.width_in_pixels
            for monName in monKeys:
                relPos = Point(xOffset, 0)
                arrangement[monName] = {"relativePos": relPos, "relativeTo": None}
                xOffset += monitors[monName]["monitor"].width_in_pixels

        else:

            for monName in monitors.keys():
                if monName == self.name:
                    relPos = relativePos
                    relTo = relativeTo
                else:
                    monitor = monitors[monName]["monitor"]
                    relPos = Point(monitor.x, monitor.y)
                    relTo = None
                arrangement[monName] = {"relativePos": relPos, "relativeTo": relTo}

        _arrangeMonitors(arrangement)

    @property
    def box(self) -> Optional[Box]:
        monitors = _XgetMonitors(self.name)
        if monitors:
            monitor = monitors[0]
            return Box(monitor.x, monitor.y, monitor.width_in_pixels, monitor.height_in_pixels)
        return None

    @property
    def rect(self) -> Optional[Rect]:
        monitors = _XgetMonitors(self.name)
        if monitors:
            monitor = monitors[0]
            return Rect(monitor.x, monitor.y, monitor.x + monitor.width_in_pixels, monitor.y + monitor.height_in_pixels)
        return None

    @property
    def scale(self) -> Optional[Tuple[float, float]]:
        return _scale(self.name)

    def setScale(self, scale: Optional[Tuple[float, float]], applyGlobally: bool = True):
        # https://askubuntu.com/questions/1193940/setting-monitor-scaling-to-200-with-xrandr
        # https://wiki.archlinux.org/title/HiDPI#GNOME
        cmd = ""
        if scale is not None and isinstance(scale, tuple):
            if "gnome" in os.environ.get('XDG_CURRENT_DESKTOP', '').lower():
                _GNOME_setGlobalScaling(applyGlobally)
                if applyGlobally:
                    targetScale = min((1.0, 2.0, 3.0), key=lambda x: abs(x-(scale[0]/100)))
                    cmd = '''gsettings set org.gnome.settings-daemon.plugins.xsettings overrides "[{'Gdk/WindowScalingFactor', <%s>}]"''' % int(targetScale)

            if not cmd and "wayland" not in os.environ.get('XDG_SESSION_TYPE', '').lower():
                scaleX, scaleY = round(100 / scale[0], 1), round(100 / scale[1], 1)
                if 0 < scaleX <= 3 and 0 < scaleY <= 3:
                    # This is simpler but may lead to blurry results...
                    cmd = "xrandr --output %s --scale %sx%s" % (self.name, scaleX, scaleY)
                    # ... try this instead? (must re-calculate monitor positions)
                    # cmd = self._buildScaleCmd((scaleX, scaleY)
            if cmd:
                _, _ = _runProc(cmd)

    def _buildScaleCmd(self, scale: Tuple[float, float]) -> str:
        # https://unix.stackexchange.com/questions/596887/how-to-scale-the-resolution-display-of-the-desktop-and-or-applications
        scaleX, scaleY = scale
        cmd = ""
        monitors = _getAllMonitorsDict()
        for monName in monitors.keys():
            monitor = monitors[monName]

            if monName == self.name:
                defMode = self.defaultMode
                if defMode is not None:
                    width, height = defMode.width, defMode.height
                    panX, panY = int(width * scaleX), int(height * scaleY)
                    newScaleX, newScaleY = scaleX, scaleY
                else:
                    return ""

            else:
                mode = monitor["size"]
                width, height = mode.width, mode.height
                panX, panY = width, height
                currScale = monitor["scale"]
                if currScale is not None:
                    newScaleX, newScaleY = currScale[0] / 100, currScale[1] / 100
                else:
                    newScaleX, newScaleY = 1, 1

            x, y = monitor["position"]

            cmd += (" --output %s --mode %sx%s --panning %sx%s --scale %sx%s --pos %sx%s %s"
                    % (monName, width, height, panX, panY, newScaleX, newScaleY, x, y,
                       "--primary" if monitor.get("is_primary", False) else ""))
        if cmd:
            cmd = "xrandr" + cmd
        return cmd

    @property
    def dpi(self) -> Optional[Tuple[float, float]]:
        monitors = _XgetMonitors(self.name)
        if monitors:
            monitor = monitors[0]
            x, y, w, h = monitor.x, monitor.y, monitor.width_in_pixels, monitor.height_in_pixels
            if monitor.width_in_millimeters != 0 and monitor.height_in_millimeters != 0:
                dpiX, dpiY = round((w * 25.4) / monitor.width_in_millimeters), round((h * 25.4) / monitor.height_in_millimeters)
            else:
                dpiX, dpiY = 0.0, 0.0
            return dpiX, dpiY
        return None

    @property
    def orientation(self) -> Optional[Union[int, Orientation]]:
        monitorData = getMonitorsData(self.handle)
        if monitorData:
            display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData[0]
            orientation = int(math.log(crtcInfo.rotation, 2))
            if orientation in (Orientation.NORMAL, Orientation.INVERTED, Orientation.LEFT, Orientation.RIGHT):
                return Orientation(int(math.log(crtcInfo.rotation, 2)))
        return None

    def setOrientation(self, orientation: Optional[Union[int, Orientation]]):
        if orientation is not None and orientation in (Orientation.NORMAL, Orientation.INVERTED, Orientation.LEFT, Orientation.RIGHT):
            global _rotations
            direction = _rotations[orientation]
            cmd = "xrandr --output %s --rotate %s" % (self.name, direction)
            _, _ = _runProc(cmd)

    @property
    def frequency(self) -> Optional[float]:
        monitorData = getMonitorsData(self.handle)
        if monitorData:
            display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData[0]
            for mode in res.modes:
                if crtcInfo.mode == mode.id:
                    if mode.h_total != 0 and mode.v_total != 0:
                        return float(round(mode.dot_clock / (mode.h_total * mode.v_total), 2))
                    else:
                        return 0.0
        return None
    refreshRate = frequency

    @property
    def colordepth(self) -> int:
        return int(self.screen.root_depth)

    @property
    def brightness(self) -> Optional[int]:
        # https://manerosss.wordpress.com/2017/05/16/brightness-linux-xrandr/
        value = None
        cmd = 'xrandr --verbose | grep %s -A 10 | grep "Brightness" | grep -o "[0-9].*"' % self.name
        code, ret = _runProc(cmd)
        if ret:
            try:
                value = int(float(ret) * 100)
            except:
                pass
        return value

    def setBrightness(self, brightness: Optional[int]):
        if brightness is not None and 0 <= brightness <= 100:
            value = brightness / 100
            if 0 <= value <= 1:
                cmd = "xrandr --output %s --brightness %s" % (self.name, str(value))
                _, _ = _runProc(cmd)

    @property
    def contrast(self) -> Optional[int]:
        value = None
        cmd = 'xrandr --verbose | grep %s -A 10 | grep "Gamma" | grep -o "[0-9].*"' % self.name
        code, ret = _runProc(cmd)
        if ret:
            try:
                r, g, b = ret.split(":")
                value = int((((1 / (float(r) or 1)) + (1 / (float(g) or 1)) + (1 / (float(b) or 1))) / 3) * 100)
            except:
                pass
        return value

    def setContrast(self, contrast: Optional[int]):
        if contrast is not None and 0<= contrast <= 100:
            value = contrast / 100
            if 0 <= value <= 1:
                rgb = str(round(value, 1))
                gamma = rgb + ":" + rgb + ":" + rgb
                cmd = "xrandr --output %s --gamma %s" % (self.name, gamma)
                _, _ = _runProc(cmd)

    @property
    def mode(self) -> Optional[DisplayMode]:
        monitorData = getMonitorsData(self.handle)
        if monitorData:
            display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData[0]
            for resMode in res.modes:
                if resMode.id == crtcInfo.mode:
                    if resMode.h_total != 0 and resMode.v_total != 0:
                        freq = round(resMode.dot_clock / (resMode.h_total * resMode.v_total), 2)
                    else:
                        freq = 0.0
                    return DisplayMode(resMode.width, resMode.height, freq)
        return None

    def setMode(self, mode: Optional[DisplayMode]):
        # https://stackoverflow.com/questions/12706631/x11-change-resolution-and-make-window-fullscreen
        # randr.set_screen_size(defaultEwmhRoot.root, mode.width, mode.height, 0, 0)
        # randr.set_screen_config(defaultEwmhRoot.root, size_id, 0, 0, round(mode.frequency), 0)
        # randr.change_output_property()
        if mode:
            cmd = "xrandr --output %s --mode %sx%s -r %s" % (self.name, mode.width, mode.height, mode.frequency)
            _, _ = _runProc(cmd)

    @property
    def defaultMode(self) -> Optional[DisplayMode]:
        # Assuming first mode is default (perhaps not the best way)
        monitorData = getMonitorsData(self.handle)
        if monitorData:
            display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData[0]
            outMode = outputInfo.modes[0]
            for resMode in res.modes:
                if outMode == resMode.id:
                    if resMode.h_total != 0 and resMode.v_total != 0:
                        freq = round(resMode.dot_clock / (resMode.h_total * resMode.v_total), 2)
                    else:
                        freq = 0.0
                    return DisplayMode(resMode.width, resMode.height, freq)
        return None

    def setDefaultMode(self):
        cmd = "xrandr --output %s --auto" % self.name
        _, _ = _runProc(cmd)

    @property
    def allModes(self) -> list[DisplayMode]:
        modes: List[DisplayMode] = []
        monitorData = getMonitorsData(self.handle)
        if monitorData:
            display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData[0]
            outputModes = outputInfo.modes
            for resMode in res.modes:
                if resMode.id in outputModes:
                    if resMode.h_total != 0 and resMode.v_total != 0:
                        freq = round(resMode.dot_clock / (resMode.h_total * resMode.v_total), 2)
                    else:
                        freq = 0.0
                    modes.append(DisplayMode(resMode.width, resMode.height, freq))
        return modes

    @property
    def isPrimary(self) -> bool:
        if isWatchdogEnabled():
            monitorData = getMonitorsData(self.handle)
            if monitorData:
                display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData[0]
                return bool(monitor.primary == 1)
        else:
            ret = randr.get_output_primary(self.root)
            if ret and hasattr(ret, "output"):
                return bool(ret.output == self.handle)
        return False

    def setPrimary(self):
        # https://smithay.github.io/smithay////x11rb/protocol/randr/fn.set_monitor.html
        if not self.isPrimary:
            cmd = "xrandr --output %s --primary" % self.name
            _, _ = _runProc(cmd)

    def turnOn(self):
        if self.isSuspended:
            cmd = "xset dpms force on"
            _, _ = _runProc(cmd)
        if not self.isOn:
            targetX = 0
            targetName = ""
            for monitor in _XgetMonitors():
                if self.name != monitor.name and targetX <= monitor.x + monitor.width_in_pixels:
                    targetX = monitor.x + monitor.width_in_pixels
                    targetName = monitor.name
            cmdPart = ""
            if targetName:
                cmdPart = " --right-of %s" % targetName
            cmd = str("xrandr --output %s --auto" % self.name) + cmdPart
            _, _ = _runProc(cmd)

    def turnOff(self):
        if self.isOn:
            cmd = "xrandr --output %s --off" % self.name
            _, _ = _runProc(cmd)

    @property
    def isOn(self) -> Optional[bool]:
        # https://stackoverflow.com/questions/3433203/how-to-determine-if-lcd-monitor-is-turned-on-from-linux-command-line
        cmd = "xrandr --listactivemonitors"
        code, ret = _runProc(cmd)
        res: Optional[bool] = None
        if ret:
            res = self.name in ret
        isSuspended = self.isSuspended
        return (res and not isSuspended) if isSuspended is not None else res

    def suspend(self):
        # xrandr has no standby option. xset doesn't allow to target just one output (it works at display level)
        if not self.isSuspended:
            cmd = "xset dpms force standby"
            _, _ = _runProc(cmd)

    @property
    def isSuspended(self) -> Optional[bool]:
        cmd = 'xset -q | grep " Monitor is "'
        code, ret = _runProc(cmd)
        if ret:
            return bool("Standby" in ret)
        return None

    def attach(self):
        # This produces the same effect that re-attaching a monitor, but will reset monitor to default mode
        targetX = 0
        targetName = ""
        for monitor in _XgetMonitors():
            if self.name != monitor.name and targetX <= monitor.x + monitor.width_in_pixels:
                targetX = monitor.x + monitor.width_in_pixels
                targetName = monitor.name
        cmdPart = ""
        if targetName:
            cmdPart = " --right-of %s" % targetName
        cmd = str("xrandr --output %s --auto" % self.name) + cmdPart
        _, _ = _runProc(cmd)

    def detach(self, permanent: bool = False):
        # Setting mode to 0 produces the same effect that detaching a monitor.
        monitorData = getMonitorsData(self.handle)
        if monitorData:
            display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData[0]
            try:
                # randr.set_crtc_config() fails in Cinnamon
                randr.set_crtc_config(self.display, crtc, Xlib.X.CurrentTime, crtcInfo.x, crtcInfo.y, 0, crtcInfo.rotation, [])
            except:
                cmd = "xrandr --output %s --mode %sx%s" % (self.name, 0, 0)
                _, _ = _runProc(cmd)

    @property
    def isAttached(self) -> bool:
        monitor = _XgetMonitors(self.name)
        return bool(monitor)


def _buildCommand(arrangement: dict[str, dict[str, Union[int, bool]]], xOffset: int, yOffset: int):
    cmd = "xrandr"
    for monName in arrangement.keys():
        arrInfo = arrangement[monName]
        cmd += " --output %s" % monName
        # xrandr won't accept negative values!!!!
        # https://superuser.com/questions/485120/how-do-i-align-the-bottom-edges-of-two-monitors-with-xrandr
        cmd += " --pos %sx%s" % (str(int(arrInfo["x"]) + xOffset), str(int(arrInfo["y"]) + yOffset))
        cmd += " --mode %sx%s" % (arrInfo["w"], arrInfo["h"])
        if arrInfo["setPrimary"]:
            cmd += " --primary"
    return cmd


def _GNOME_isScalingGlobal() -> Optional[bool]:
    cmd = '''gsettings get org.gnome.mutter experimental-features'''
    try:
        proc = subprocess.run(cmd, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if "wayland" in os.environ.get('XDG_SESSION_TYPE', '').lower():
            return bool("scale-monitor-framebuffer" not in proc.stdout)
        else:
            return bool("x11-randr-fractional-scaling" not in proc.stdout)
    except:
        pass
    return None


def _GNOME_setGlobalScaling(setGlobal=True):
    if setGlobal:
        cmd = '''gsettings set org.gnome.mutter experimental-features "[]"'''
        _, _ = _runProc(cmd)
    else:
        cmd = ""
        if "wayland" in os.environ.get('XDG_SESSION_TYPE', '').lower():
            try:
                proc = subprocess.run("grep -sl mutter /proc/*/maps", text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if "/maps" in proc.stdout:
                    cmd = '''gsettings set org.gnome.mutter experimental-features "['scale-monitor-framebuffer']"'''
            except:
                pass
        else:
            cmd = '''gsettings set org.gnome.mutter experimental-features "['x11-randr-fractional-scaling']"'''
        if cmd:
            _, _ = _runProc(cmd)
  
                    
def _GNOME_getScalingFactor() -> Optional[int]:
    cmd = '''gsettings get org.gnome.settings-daemon.plugins.xsettings overrides'''
    code, ret = _runProc(cmd)
    if "WindowScalingFactor" in ret:
        try:
            return int(ret.split("WindowScalingFactor': <")[1][0])
        except:
            pass
    return None


# def _MUTTER_getMonitorsInfo() -> Tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
#     # https://askubuntu.com/questions/1035718/how-change-display-scale-from-the-command-line-in-ubuntu-18-04-xorg
#     # https://github.com/jadahl/gnome-monitor-config/blob/master/src/org.gnome.Mutter.DisplayConfig.xml
#     # https://askubuntu.com/questions/253910/does-kwin-have-a-d-bus-api
#     # https://blog.fpmurphy.com/2012/02/d-bus-cinnamon-and-the-gnome-shell.html
#     # https://bbs.archlinux.org/viewtopic.php?id=278808
#
#     #     # https://stackoverflow.com/questions/47026351/change-backlight-brightness-in-linux-with-python
#     #     os.system('gdbus call --session '
#     #               '--dest org.gnome.SettingsDaemon.Power '
#     #               '--object-path /org/gnome/SettingsDaemon/Power '
#     #               '--method org.freedesktop.DBus.Properties.Set org.gnome.SettingsDaemon.Power.Screen '
#     #               'Brightness "<int32 %s>"' % str(brightness))
#     #     os.system('gdbus call --session '
#     #               '--dest org.gnome.SettingsDaemon.Power '
#     #               '--object-path /org/gnome/SettingsDaemon/Power '
#     #               '--method org.freedesktop.DBus.Properties.Get org.gnome.SettingsDaemon.Power.Screen '
#     #               'Brightness')
#
#     try:
#         import dbus
#     except:
#         return {}, {}, {}
#
#     namespace = "org.gnome.Mutter.DisplayConfig"
#     dbus_path = "/org/gnome/Mutter/DisplayConfig"
#
#     session_bus = dbus.SessionBus()
#     obj = session_bus.get_object(namespace, dbus_path)
#     interface = dbus.Interface(obj, dbus_interface=namespace)
#
#     serial, connected_monitors, logical_monitors, general_config = interface.GetCurrentState()
#
#     connectedInfo = {}
#     for monitor in connected_monitors:
#         monName = monitor[0][0]
#         current_mode = {}
#         default_mode = {}
#         availableModes = {}
#         scale = None
#         availableScales = []
#         for mode in monitor[1]:
#             modeName, width, height, freq, scale, scales = mode[:6]
#             availableModes[str(modeName)] = {"width": int(width), "height": int(height), "frequency": float(freq)}
#             if len(mode) >= 7:
#                 if mode[6].get("is-current", 0):
#                     current_mode = {"name": str(modeName), "width": int(width), "height": int(height), "frequency": float(freq)}
#                     availableScales = [float(value) for value in scales]
#                 if mode[6].get("is-preferred", 0):
#                     default_mode = {"name": str(modeName), "width": int(width), "height": int(height), "frequency": float(freq)}
#         connectedInfo[str(monName)] = {"current_mode": current_mode, "default_mode": default_mode,
#                                        "available_modes": availableModes, "scale": float(scale), "available_scales": availableScales}
#     logicalInfo = {}
#     for monIndex, logMon in enumerate(logical_monitors):
#         x, y, scale, transform, primary, monitors, props = logMon
#         monsNames = [str(name) for name in monitors[0] if name and name != 'unknown']
#         logicalInfo[str(monIndex)] = {"position": Point(int(x), int(y)), "scale": float(scale), "transform": int(transform),
#                                       "is_primary": int(primary), "props": dict(props), "monitors": monsNames}
#     return connectedInfo, logicalInfo, dict(general_config)
#
#
# def _MUTTER_setMonitorConfig(name: str, x: int, y: int, scale: float, transform: int, primary: bool, modeName: str, monInfo: dict[str, dict]):
#     # https://askubuntu.com/questions/1035718/how-change-display-scale-from-the-command-line-in-ubuntu-18-04-xorg
#     # Just a test. Not properly working at all!!!
#
#     try:
#         import dbus
#     except:
#         return
#
#     namespace = "org.gnome.Mutter.DisplayConfig"
#     dbus_path = "/org/gnome/Mutter/DisplayConfig"
#
#     session_bus = dbus.SessionBus()
#     obj = session_bus.get_object(namespace, dbus_path)
#     interface = dbus.Interface(obj, dbus_interface=namespace)
#
#     # ApplyMonitorsConfig() needs (connector name, mode ID) for each connected
#     # monitor of a logical monitor, but GetCurrentState() only returns the
#     # connector name for each connected monitor of a logical monitor. So iterate
#     # through the globally connected monitors to find the mode ID.
#     serial, connected_monitors, logical_monitors, general_config = interface.GetCurrentState()
#
#     # If someday updating this script: a logical monitor may appear on multiple
#     # connected monitors due to mirroring.
#     monConfig = []
#     for logMon in logical_monitors:
#         x, y, scale, transform, primary, monitors, props = logMon
#         monsNames = [str(name) for name in monitors[0]]
#         for info in monInfo:
#             monName, modeName, _ = info
#             if monName in monsNames:
#                 monConfig.append([x, y, scale, transform, primary, info])
#                 break
#
#     # Change the 1 to a 2 if you want a "Revert Settings / Keep Changes" dialog
#     interface.ApplyMonitorsConfig(serial, 1, monConfig, {})


def _scale(name: str) -> Optional[Tuple[float, float]]:
    if "gnome" in os.environ.get('XDG_CURRENT_DESKTOP', '').lower() and _GNOME_isScalingGlobal():
        value = _GNOME_getScalingFactor()
        if value is not None:
            scaleX, scaleY = value * 100.0, value * 100.0
            return scaleX, scaleY

    if "wayland" not in os.environ.get('XDG_SESSION_TYPE', '').lower():
        value = None
        cmd = 'xrandr -q | grep %s -A 5 | grep " +\\|*+"' % name
        code, ret = _runProc(cmd)
        if ret:
            try:
                res = ret.split(" ")
                lines: List[str] = list(filter(None, res))
                a, b = lines[0].split("x")
                w = int(a)
                h = int(b)
                r = float(lines[1].replace("+", "").replace("*", ""))
                value = DisplayMode(w, h, r)
            except:
                pass
        if value:
            monitors = _XgetMonitors(name)
            if monitors:
                monitor = monitors[0]
                w, h = monitor.width_in_pixels, monitor.height_in_pixels
                wm, hm = monitor.width_in_millimeters, monitor.height_in_millimeters
                if wm and hm:
                    wDef, hDef = value.width, value.height
                    dpiXDef, dpiYDef = round((wDef * 25.4) / wm), round((hDef * 25.4) / hm)
                    dpiX, dpiY = round((w * 25.4) / wm), round((h * 25.4) / hm)
                    if dpiX and dpiY and dpiXDef and dpiYDef:
                        scaleX, scaleY = (100 / (dpiX / dpiXDef), 100 / (dpiY / dpiYDef))
                        return scaleX, scaleY
    return None


def _runProc(cmd: str):
    try:
        # Some commands will take some time to be executed and return required value
        proc = subprocess.run(cmd, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) #, timeout=3)
        return proc.returncode, proc.stdout
    except:
        pass
    return -1, ""


class _Monitor(NamedTuple):
    name: str
    primary: int
    x: int
    y: int
    width_in_pixels: int
    height_in_pixels: int
    width_in_millimeters: int
    height_in_millimeters: int
    crtcs: List[int]


def _getMonitorsData(handle: Optional[int] = None) -> (
                        List[Tuple[Xlib.display.Display, Struct, XWindow, randr.GetScreenResourcesCurrent,
                        randr.MonitorInfo, str, int, randr.GetOutputInfo, int, randr.GetCrtcInfo]]):
    monitors: List[Tuple[Xlib.display.Display, Struct, XWindow, randr.GetScreenResourcesCurrent,
                         randr.MonitorInfo, str, int, randr.GetOutputInfo, int, randr.GetCrtcInfo]] = []
    stopSearching = False
    roots: List[Tuple[Xlib.display.Display, Struct, XWindow]] = getRoots()
    for rootData in roots:
        display: Xlib.display.Display = rootData[0]
        screen: Struct = rootData[1]
        root: XWindow = rootData[2]
        try:
            mons = randr.get_monitors(root).monitors
        except:
            # In Cinnamon randr extension has no get_monitors() method (?!?!?!?)
            mons = _RgetAllMonitors()
            stopSearching = True
        for monitor in mons:
            if isinstance(monitor.name, int):
                monitor.name = display.get_atom_name(monitor.name)
            res = randr.get_screen_resources_current(root)
            output = monitor.crtcs[0]
            outputInfo = randr.get_output_info(display, output, res.config_timestamp)
            if outputInfo.crtc:
                if handle:
                    if handle == output:
                        crtcInfo = randr.get_crtc_info(display, outputInfo.crtc, res.config_timestamp)
                        return [(display, screen, root, res, monitor, monitor.name, output, outputInfo, outputInfo.crtc, crtcInfo)]
                else:
                    crtcInfo = randr.get_crtc_info(display, outputInfo.crtc, res.config_timestamp)
                    monitors.append((display, screen, root, res, monitor, monitor.name, output, outputInfo, outputInfo.crtc, crtcInfo))
        if stopSearching:
            break
    return monitors


def _XgetAllMonitors(name: str = ""):
    monitors = []
    if isWatchdogEnabled():
        for monitorData in getMonitorsData():
            display, screen, root, res, monitor, monName, output, outputInfo, crtc, crtcInfo = monitorData
            if name:
                if name and name == monName:
                    return [(display, screen, root, monitor, monName)]
            else:
                monitors.append((display, screen, root, monitor, monName))
    else:
        stopSearching = False
        roots: List[Tuple[Xlib.display.Display, Struct, XWindow]] = getRoots()
        for rootData in roots:
            display: Xlib.display.Display = rootData[0]
            screen: Struct = rootData[1]
            root: XWindow = rootData[2]
            try:
                mons = randr.get_monitors(root).monitors
            except:
                # In Cinnamon randr extension has no get_monitors() method (?!?!?!?)
                mons = _RgetAllMonitors()
                stopSearching = True
            for monitor in mons:
                if isinstance(monitor.name, int):
                    monitor.name = display.get_atom_name(monitor.name)
                if name:
                    if name == monitor.name:
                        return [(display, screen, root, monitor, monitor.name)]
                else:
                    monitors.append((display, screen, root, monitor, monitor.name))
            if stopSearching:
                break
    return monitors


def _RgetAllMonitors():
    # Check if this works in actual Cinnamon
    monitors: List[_Monitor] = []
    outputDict = {}
    for outputData in _XgetAllOutputs():
        display, screen, root, output, outputInfo = outputData
        outputDict[outputInfo.name] = {"outputData": outputData}

    namesData = _RgetMonitorsInfo()
    for item in namesData:
        monName, primary, x, y, w, h = item
        if monName in outputDict.keys():
            display, screen, root, output, outputInfo = outputDict[monName]["outputData"]
            wm, hm = outputInfo.mm_width, outputInfo.mm_height
            crtcs = [output]
            monitors.append(_Monitor(monName, primary, x, y, w, h, wm, hm, crtcs))
    return monitors


def _RgetMonitorsInfo(activeOnly: bool = True):
    monInfo = []
    cmd = "xrandr -q | grep %s" % ("' connected '" if activeOnly else "'connected '")
    code, ret = _runProc(cmd)
    if ret:
        try:
            lines = ret.split("\n")[:-1]
            for line in lines:
                items = line.split(" ")
                name = items[0]
                if name:
                    primary = 1 if "primary" in items[2] else 0
                    info = items[2 + primary]
                    if "x" in info and "+" in info:
                        parts = info.split("+")
                        x = parts[1]
                        y = parts[2]
                        w, h = parts[0].split("x")
                        monInfo.append((name, primary, int(x), int(y), int(w), int(h)))
        except:
            pass
    return monInfo


def _XgetAllOutputs(name: str = ""):
    outputs: List[Tuple[Xlib.display.Display, Xlib.protocol.rq.Struct, Xlib.xobject.drawable.Window,
                        int, randr.GetOutputInfo]] = []
    roots: List[Tuple[Xlib.display.Display, Struct, XWindow]] = getRoots()
    for rootData in roots:
        display: Xlib.display.Display = rootData[0]
        screen: Struct = rootData[1]
        root: XWindow = rootData[2]
        res = randr.get_screen_resources_current(root)
        for output in res.outputs:
            outputInfo = randr.get_output_info(display, output, res.config_timestamp)
            if os.environ.get('DESKTOP_SESSION', "").lower() == "cinnamon" and outputInfo.name.startswith("ual"):
                outputInfo.name = _fixCinnamonName(outputInfo.name)
            if name:
                if name == outputInfo.name and outputInfo.crtc:
                    return [(display, screen, root, output, outputInfo)]
            else:
                outputs.append((display, screen, root, output, outputInfo))
    return outputs


_cinnamon_names = []
if os.environ.get('DESKTOP_SESSION', "").lower() == "cinnamon":
    _cinnamon_names = [item[0] for item in _RgetMonitorsInfo(False)]


def _fixCinnamonName(outputName: str):
    # in Cinnamon VMs, output.name seems to be cut to the last 4 chars
    outName = outputName
    global _cinnamon_names
    for name in _cinnamon_names:
        if name.endswith(outputName):
            outName = name
            break
    return outName


def _XgetMonitors(name: str = ""):
    monitors = []
    for monitorData in _XgetAllMonitors(name):
        display, screen, root, monitor, monName = monitorData
        monitors.append(monitor)
    return monitors


def _XgetMonitorsDict():
    monitors = {}
    for monitorData in _XgetAllMonitors():
        display, screen, root, monitor, monName = monitorData
        monitors[monName] = {"monitor": monitor}
    return monitors


def _XgetMonitorData(handle: Optional[int] = None) -> Optional[Tuple[Xlib.display.Display, Struct, XWindow, randr.MonitorInfo, int, str]]:
    for monitorData in _XgetAllMonitors():
        display, screen, root, monitor, monName = monitorData
        output = monitor.crtcs[0]
        if (handle and handle == output) or (not handle and monitor.primary == 1):
            return display, screen, root, monitor, output, monName
    return None


def _checkEnvironment():

    # Check if randr extension is available
    if not defaultEwmhRoot.display.has_extension('RANDR'):
        sys.stderr.write('{}: server does not have the RANDR extension\n'.format(sys.argv[0]))
        ext = defaultEwmhRoot.display.query_extension('RANDR')
        print(ext)
        sys.stderr.write("\n".join(defaultEwmhRoot.display.list_extensions()))
        if ext is None:
            sys.exit(1)

    # Check if Xorg is running and xset is present (this will not work on Wayland or alike)
    cmd = "xset -q"
    code, ret = _runProc(cmd)
    if not ret:
        sys.stderr.write("{}: xset is not available. 'suspend' and 'isSuspended' methods will not work\n".format(sys.argv[0]))

    # Check if xrandr is present (it will not in distributions like Arch or Manjaro)
    cmd = "xrandr -q"
    code, ret = _runProc(cmd)
    if not ret:
        sys.stderr.write(
            '{}: Xorg and/or xrandr are not available\n'.format(sys.argv[0]))
        sys.exit(1)
_checkEnvironment()


def _eventLoop(kill: threading.Event, interval: float):

    randr.select_input(defaultEwmhRoot.root,
                       randr.RRScreenChangeNotifyMask
                       | randr.RRCrtcChangeNotifyMask
                       | randr.RROutputChangeNotifyMask
                       | randr.RROutputPropertyNotifyMask
    )

    while not kill.is_set():

        count = defaultEwmhRoot.display.pending_events()
        while count > 0 and not kill.is_set():

            e = defaultEwmhRoot.display.next_event()

            if e.__class__.__name__ == randr.ScreenChangeNotify.__name__:
                print('Screen change')
                print(e._data)

            # check if we're getting one of the RandR event types with subcodes
            elif e.type == defaultEwmhRoot.display.extension_event.CrtcChangeNotify[0]:
                # yes, check the subcodes

                # CRTC information has changed
                if (e.type, e.sub_code) == defaultEwmhRoot.display.extension_event.CrtcChangeNotify:
                    print('CRTC change')
                    # e = randr.CrtcChangeNotify(display=display.display, binarydata = e._binary)
                    print(e._data)

                # Output information has changed
                elif (e.type, e.sub_code) == defaultEwmhRoot.display.extension_event.OutputChangeNotify:
                    print('Output change')
                    # e = randr.OutputChangeNotify(display=display.display, binarydata = e._binary)
                    print(e._data)

                # Output property information has changed
                elif (e.type, e.sub_code) == defaultEwmhRoot.display.extension_event.OutputPropertyNotify:
                    print('Output property change')
                    # e = randr.OutputPropertyNotify(display=display.display, binarydata = e._binary)
                    print(e._data)

                else:
                    print("Unrecognised subcode", e.sub_code)

            count -= 1
        kill.wait(interval)

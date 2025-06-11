#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
assert sys.platform == "win32"

import gc
import platform
import threading
import time

import ctypes.wintypes
import pywintypes
from typing import Optional, List, Union, Tuple, cast
import win32api
import win32gui
import win32con
import win32evtlog

from ._main import (BaseMonitor, _getRelativePosition,
                    DisplayMode, ScreenValue, Box, Rect, Point, Size, Position, Orientation)
from ._structs import (_QDC_ONLY_ACTIVE_PATHS, _DISPLAYCONFIG_PATH_INFO, _DISPLAYCONFIG_MODE_INFO, _LUID,
                       _DISPLAYCONFIG_SOURCE_DPI_SCALE_GET, _DISPLAYCONFIG_SOURCE_DPI_SCALE_SET, _DPI_VALUES,
                       _DISPLAYCONFIG_DEVICE_INFO_GET_DPI_SCALE, _DISPLAYCONFIG_DEVICE_INFO_SET_DPI_SCALE,
                       _DISPLAYCONFIG_SOURCE_DEVICE_NAME, _DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
                       )


# Thanks to lappely (https://github.com/poipoiPIO) for his HELP!!!
try:
    dpiAware = ctypes.windll.user32.GetAwarenessFromDpiAwarenessContext(ctypes.windll.user32.GetThreadDpiAwarenessContext())
except AttributeError:  # Windows server does not implement GetAwarenessFromDpiAwarenessContext
    dpiAware = 0

if dpiAware == 0:
    # It seems that this can't be invoked twice. Setting it to 1 for apps having 0 (unaware) may have less impact
    ctypes.windll.shcore.SetProcessDpiAwareness(1)


def _getAllMonitors() -> list[Win32Monitor]:
    # Monitors IDs may change in case of one of them is attached / detached / plugged / unplugged
    monitors: list[Win32Monitor] = []
    mons = win32api.EnumDisplayMonitors()
    for mon in mons:
        hMon = mon[0].handle
        try:
            monitors.append(Win32Monitor(hMon))
        except:
            pass
    return monitors


def _getAllMonitorsDict() -> dict[str, ScreenValue]:
    # https://stackoverflow.com/questions/35814309/winapi-changedisplaysettingsex-does-not-work
    result: dict[str, ScreenValue] = {}
    monitors = _win32getAllMonitorsDict()
    for monName in monitors:
        hMon = monitors[monName]["hMon"]
        monitorInfo = monitors[monName]["monitor"]

        x, y, r, b = monitorInfo["Monitor"]
        wx, wy, wr, wb = monitorInfo["Work"]
        is_primary = monitorInfo.get("Flags", 0) == win32con.MONITORINFOF_PRIMARY
        pScale = ctypes.c_uint()
        ctypes.windll.shcore.GetScaleFactorForMonitor(hMon, ctypes.byref(pScale))
        scale = pScale.value
        dpiX = ctypes.c_uint()
        dpiY = ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(hMon, 0, ctypes.byref(dpiX), ctypes.byref(dpiY))
        try:
            settings = win32api.EnumDisplaySettings(monName, win32con.ENUM_CURRENT_SETTINGS)
        except:
            try:
                settings = win32api.EnumDisplaySettings(monName, win32con.ENUM_REGISTRY_SETTINGS)
            except:
                continue

        rot = Orientation(settings.DisplayOrientation)
        freq = settings.DisplayFrequency
        depth = settings.BitsPerPel

        result[monName] = {
            "system_name": monName,
            "id": hMon,
            "is_primary": is_primary,
            "position": Point(x, y),
            "size": Size(abs(r - x), abs(b - y)),
            "workarea": Rect(wx, wy, wr, wb),
            "scale": (scale, scale),
            "dpi": (dpiX.value, dpiY.value),
            "orientation": rot,
            "frequency": freq,
            "colordepth": depth
        }
    return result


def _getMonitorsCount() -> int:
    return len(win32api.EnumDisplayMonitors())


def _findMonitor(x: int, y: int) -> List[Win32Monitor]:
    # Watch this: started to fail when repeatedly and quickly invoking it in Python 3.10 (it was ok in 3.9)
    hMon = win32api.MonitorFromPoint((x, y), win32con.MONITOR_DEFAULTTONEAREST)
    if hMon and hasattr(hMon, "handle"):
        try:
            return [Win32Monitor(hMon.handle)]
        except:
            pass
    return []


def _getPrimary() -> Win32Monitor:
    return Win32Monitor()


def _arrangeMonitors(arrangement: dict[str, dict[str, Optional[Union[str, int, Position, Point, Size]]]]):
    # https://stackoverflow.com/questions/35814309/winapi-changedisplaysettingsex-does-not-work
    # https://stackoverflow.com/questions/195267/use-windows-api-from-c-sharp-to-set-primary-monitor
    monitors = _win32getAllMonitorsDict()
    primaryPresent = False
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
            primaryPresent = True
    if not primaryPresent:
        return

    newPos: dict[str, dict[str, int]] = {}

    devmode = pywintypes.DEVMODEType()  # type: ignore[attr-defined]
    devmode.Position_x = 0
    devmode.Position_y = 0
    devmode.Fields = win32con.DM_POSITION
    flags = win32con.CDS_SET_PRIMARY | win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET

    win32api.ChangeDisplaySettingsEx(setAsPrimary, devmode, flags)
    newPos[setAsPrimary] = {"x": 0, "y": 0}

    for monName in arrangement.keys():

        if monName != setAsPrimary:

            relativePos: Union[Position, int, Point, Tuple[int, int]] = arrangement[monName]["relativePos"]

            if isinstance(relativePos, Position) or isinstance(relativePos, int):

                targetMonInfo = monitors[monName]["monitor"]
                x, y, r, b = targetMonInfo["Monitor"]
                w = abs(r - x)
                h = abs(b - y)
                relativeTo = str(arrangement[monName]["relativeTo"])
                targetMon = {"relativePos": relativePos, "relativeTo": relativeTo,
                             "position": Point(x, y), "size": Size(w, h)}

                relMonInfo = monitors[relativeTo]["monitor"]
                x, y, r, b = relMonInfo["Monitor"]
                if relativeTo in newPos.keys():
                    relX, relY = newPos[relativeTo]["x"], newPos[relativeTo]["y"]
                else:
                    relX, relY = x, y
                w = abs(r - x)
                h = abs(b - y)
                relMon = {"position": Point(relX, relY), "size": Size(w, h)}
                x, y = _getRelativePosition(targetMon, relMon)

            else:
                x, y = relativePos

            devmode = pywintypes.DEVMODEType()  # type: ignore[attr-defined]
            devmode.Position_x = x
            devmode.Position_y = y
            devmode.Fields = win32con.DM_POSITION
            flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET

            win32api.ChangeDisplaySettingsEx(monName, devmode, flags)
            newPos[monName] = {"x": x, "y": y}

    win32api.ChangeDisplaySettingsEx()


def _getMousePos() -> Point:
    x, y = win32api.GetCursorPos()
    return Point(x, y)


class Win32Monitor(BaseMonitor):

    def __init__(self, handle: Optional[int] = None):
        """
        Class to access all methods and functions to get info and manage monitors plugged to the system.

        This class is not meant to be directly instantiated. Instead, use convenience functions like getAllMonitors(),
        getPrimary() or findMonitor(x, y).

        It can raise ValueError exception in case provided handle is not valid
        """
        if not handle:
            hMon = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
            if hMon and hasattr(hMon, "handle"):
                handle = hMon.handle
        if handle:
            monitorInfo = win32api.GetMonitorInfo(handle)
            self.handle = handle
            self.name = monitorInfo.get("Device", "")
        else:
            raise ValueError
        self._hasVCPSupport: Optional[bool] = None
        self._hasVCPPowerSupport: Optional[bool] = None
        self._sourceAdapterId: Optional[_LUID] = None
        self._sourceId: Optional[int] = None
        self._isWindows11 = False
        try:
            self._isWindows11 = bool(int(platform.win32_ver()[1].rsplit(".", 1)[1]) >= 22000)
        except:
            self._isWindows11 = False

    @property
    def size(self) -> Optional[Size]:
        monitorInfo = _getMonitorInfo(self.handle)
        if monitorInfo:
            x, y, r, b = monitorInfo["Monitor"]
            if x is not None:
                return Size(abs(r - x), abs(b - y))
        return None

    @property
    def workarea(self) -> Optional[Rect]:
        monitorInfo = _getMonitorInfo(self.handle)
        if monitorInfo:
            wx, wy, wr, wb = monitorInfo["Work"]
            if wx is not None:
                return Rect(wx, wy, wr, wb)
        return None

    @property
    def position(self) -> Optional[Point]:
        monitorInfo = _getMonitorInfo(self.handle)
        if monitorInfo:
            x, y, r, b = monitorInfo["Monitor"]
            if x is not None:
                return Point(x, y)
        return None

    def setPosition(self, relativePos: Union[int, Position, Point, Tuple[int, int]], relativeTo: Optional[str]):
        # https://stackoverflow.com/questions/35814309/winapi-changedisplaysettingsex-does-not-work
        # https://stackoverflow.com/questions/195267/use-windows-api-from-c-sharp-to-set-primary-monitor
        arrangement: dict[str, dict[str, Optional[Union[str, int, Position, Point, Size]]]] = {}
        monitors = _win32getAllMonitorsDict()
        monKeys = list(monitors.keys())
        if relativePos == Position.PRIMARY or relativePos == (0, 0):
            if self.isPrimary:
                return
            # For homogeneity, placing PRIMARY at (0, 0) and all the rest to RIGHT_TOP
            try:
                index = monKeys.index(self.name)
                monKeys.pop(index)
            except:
                return
            arrangement[self.name] = {"relativePos": Position.PRIMARY, "relativeTo": None}
            x, y, r, b = monitors[self.name]["monitor"]["Monitor"]
            xOffset = abs(r - x)

            for monName in monKeys:
                relPos = Point(xOffset, 0)
                arrangement[monName] = {"relativePos": relPos, "relativeTo": None}
                x, y, r, b = monitors[monName]["monitor"]["Monitor"]
                xOffset += abs(r - x)

        else:

            for monName in monKeys:
                if monName == self.name:
                    relPos = relativePos
                    relTo = relativeTo
                else:
                    x, y, r, b = monitors[monName]["monitor"]["Monitor"]
                    if (x, y) == (0, 0):
                        relPos = Position.PRIMARY
                    else:
                        relPos = Point(x, y)
                    relTo = None
                arrangement[monName] = {"relativePos": relPos, "relativeTo": relTo}

        _arrangeMonitors(arrangement)

    @property
    def box(self) -> Optional[Box]:
        monitorInfo = _getMonitorInfo(self.handle)
        if monitorInfo:
            x, y, r, b = monitorInfo["Monitor"]
            if x is not None:
                return Box(x, y, abs(r - x), abs(b - y))
        return None

    @property
    def rect(self) -> Optional[Rect]:
        monitorInfo = _getMonitorInfo(self.handle)
        if monitorInfo:
            x, y, r, b = monitorInfo["Monitor"]
            if x is not None:
                return Rect(x, y, r, b)
        return None

    @property
    def scale(self) -> Optional[Tuple[float, float]]:
        pScale = ctypes.c_uint()
        ctypes.windll.shcore.GetScaleFactorForMonitor(self.handle, ctypes.byref(pScale))
        # import wmi
        # obj = wmi.WMI().Win32_PnPEntity(ConfigManagerErrorCode=0)
        # displays = [x for x in obj if 'DISPLAY' in str(x)]
        # for item in displays:
        #     print(item)
        return float(pScale.value), float(pScale.value)

    def _getPaths(self) -> Tuple[Optional[_LUID], Optional[int]]:

        flags = _QDC_ONLY_ACTIVE_PATHS
        numPathArrayElements = ctypes.c_uint32()
        numModeInfoArrayElements = ctypes.c_uint32()
        ctypes.windll.user32.GetDisplayConfigBufferSizes(flags,
                                                         ctypes.byref(numPathArrayElements),
                                                         ctypes.byref(numModeInfoArrayElements))

        paths = (_DISPLAYCONFIG_PATH_INFO * numPathArrayElements.value)()
        modes = (_DISPLAYCONFIG_MODE_INFO * numModeInfoArrayElements.value)()
        nullptr = ctypes.c_void_p()
        ret = ctypes.windll.user32.QueryDisplayConfig(flags,
                                                      ctypes.byref(numPathArrayElements),
                                                      ctypes.byref(paths),
                                                      ctypes.byref(numModeInfoArrayElements),
                                                      ctypes.byref(modes),
                                                      nullptr
                                                      )
        if ret == 0:
            for path in paths:
                sourceName = _DISPLAYCONFIG_SOURCE_DEVICE_NAME()
                sourceName.header.type = _DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
                sourceName.header.size = ctypes.sizeof(sourceName)
                sourceName.header.adapterId = path.sourceInfo.adapterId
                # There must be a more canonical way to find existing path.sourceInfo.sourceId... but HOW???
                i = 0
                while True:
                    sourceName.header.id = i
                    ret = ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(sourceName))
                    if ret == 0:
                        if sourceName.viewGdiDeviceName == self.name:
                            return path.sourceInfo.adapterId, i
                    else:
                        break
                    i += 1
        return None, None

    def setScale(self, scale: Optional[Tuple[float, float]], applyGlobally: bool = True):

        if scale is not None and isinstance(scale, tuple) and scale[0] >= 100 and scale[1] >= 100:
            # https://github.com/lihas/windows-DPI-scaling-sample/blob/master/DPIHelper/DpiHelper.cpp
            # https://github.com/lihas/windows-DPI-scaling-sample/blob/master/DPIHelper/DpiHelper.cpp
            # HOW to GET adapterId and sourceId values???? -> QueryDisplayConfig
            # https://stackoverflow.com/questions/67332814/how-to-properly-clone-and-extend-two-specific-monitors-on-windows
            # Seriously all that to just get the adapterId and the sourceId???? I definitely love you, MS©

            if self._sourceAdapterId is None:
                self._sourceAdapterId, self._sourceId = self._getPaths()
                if self._sourceAdapterId is None:
                    self._sourceAdapterId = 0
                    self._sourceId = None

            if self._sourceAdapterId is not None and self._sourceId is not None:

                scaleData = _DISPLAYCONFIG_SOURCE_DPI_SCALE_GET()
                scaleData.header.type = _DISPLAYCONFIG_DEVICE_INFO_GET_DPI_SCALE
                scaleData.header.size = ctypes.sizeof(scaleData)
                scaleData.header.adapterId = self._sourceAdapterId
                scaleData.header.id = self._sourceId
                ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(scaleData))
                minScale = _DPI_VALUES[scaleData.minScaleRel]
                maxScale = _DPI_VALUES[scaleData.maxScaleRel]

                scaleValue: int = int(scale[0])
                targetScale = -1
                if scaleValue < minScale:
                    targetScale = 0
                elif scaleValue > maxScale:
                    targetScale = len(_DPI_VALUES) - 1
                else:
                    try:
                        targetScale = _DPI_VALUES.index(scaleValue)
                    except:
                        for i, value in enumerate(_DPI_VALUES):
                            targetScale = i
                            if value > scaleValue:
                                break
                if targetScale >= 0:
                    setScaleData = _DISPLAYCONFIG_SOURCE_DPI_SCALE_SET()
                    setScaleData.header.type = _DISPLAYCONFIG_DEVICE_INFO_SET_DPI_SCALE
                    setScaleData.header.size = ctypes.sizeof(setScaleData)
                    setScaleData.header.adapterId = self._sourceAdapterId
                    setScaleData.header.id = self._sourceId
                    setScaleData.scaleRel = targetScale
                    ctypes.windll.user32.DisplayConfigSetDeviceInfo(ctypes.byref(setScaleData))

    @property
    def dpi(self) -> Optional[Tuple[float, float]]:
        dpiX = ctypes.c_uint()
        dpiY = ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(self.handle, 0, ctypes.byref(dpiX), ctypes.byref(dpiY))
        return dpiX.value, dpiY.value

    @property
    def orientation(self) -> Optional[Union[int, Orientation]]:
        # Settings content: http://timgolden.me.uk/pywin32-docs/PyDEVMODE.html
        settings = None
        try:
            settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_CURRENT_SETTINGS)
        except:
            try:
                settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_REGISTRY_SETTINGS)
            except:
                pass
        if settings:
            return Orientation(settings.DisplayOrientation)
        return None

    def setOrientation(self, orientation: Optional[Union[int, Orientation]]):
        if orientation is not None and orientation in (Orientation.NORMAL, Orientation.INVERTED, Orientation.LEFT, Orientation.RIGHT):
            # In most cases an empty struct is required, but in this case we need to retrieve Display Settings first
            try:
                settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_CURRENT_SETTINGS)
            except:
                try:
                    settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_REGISTRY_SETTINGS)
                except:
                    return
            devmode = cast(pywintypes.DEVMODEType, settings)  # type: ignore[attr-defined, name-defined]
            if (settings.DisplayOrientation + orientation) % 2 == 1:
                devmode.PelsWidth, devmode.PelsHeight = devmode.PelsHeight, devmode.PelsWidth
            devmode.DisplayOrientation = orientation
            # Not working if setting Fields (!?!?!?)
            # devmode.Fields = devmode.Fields | win32con.DM_DISPLAYORIENTATION | win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
            win32api.ChangeDisplaySettingsEx(self.name, devmode,win32con.CDS_RESET | win32con.CDS_UPDATEREGISTRY)
            # win32api.ChangeDisplaySettingsEx()

    @property
    def frequency(self) -> Optional[float]:
        settings = None
        try:
            settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_CURRENT_SETTINGS)
        except:
            try:
                settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_REGISTRY_SETTINGS)
            except:
                pass
        if settings:
            return settings.DisplayFrequency
        return None
    refreshRate = frequency

    @property
    def colordepth(self) -> Optional[int]:
        settings = None
        try:
            settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_CURRENT_SETTINGS)
        except:
            try:
                settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_REGISTRY_SETTINGS)
            except:
                pass
        if settings:
            return settings.BitsPerPel
        return None

    @property
    def brightness(self) -> Optional[int]:
        minBright = ctypes.c_uint()
        currBright = ctypes.c_uint()
        maxBright = ctypes.c_uint()
        hDevices = _win32getPhysicalMonitorsHandles(self.handle)
        for hDevice in hDevices:
            ret = ctypes.windll.dxva2.GetMonitorBrightness(hDevice, ctypes.byref(minBright), ctypes.byref(currBright),
                                                           ctypes.byref(maxBright))
            _win32destroyPhysicalMonitors(hDevices)
            if ret != 0:
                return currBright.value
        return None

    def setBrightness(self, brightness: Optional[int]):
        if brightness is not None and 0 <= brightness <= 100:
            minBright = ctypes.c_uint()
            currBright = ctypes.c_uint()
            maxBright = ctypes.c_uint()
            hDevices = _win32getPhysicalMonitorsHandles(self.handle)
            for hDevice in hDevices:
                ctypes.windll.dxva2.GetMonitorBrightness(hDevice, ctypes.byref(minBright), ctypes.byref(currBright),
                                                         ctypes.byref(maxBright))
                if brightness < minBright.value:
                    brightness = minBright.value
                elif brightness > maxBright.value:
                    brightness = maxBright.value
                ctypes.windll.dxva2.SetMonitorBrightness(hDevice, brightness)
                ctypes.windll.dxva2.DestroyPhysicalMonitor(hDevice)

    @property
    def contrast(self) -> Optional[int]:
        minCont = ctypes.c_uint()
        currCont = ctypes.c_uint()
        maxCont = ctypes.c_uint()
        hDevices = _win32getPhysicalMonitorsHandles(self.handle)
        for hDevice in hDevices:
            ret = ctypes.windll.dxva2.GetMonitorContrast(hDevice, ctypes.byref(minCont), ctypes.byref(currCont),
                                                         ctypes.byref(maxCont))
            _win32destroyPhysicalMonitors(hDevices)
            if ret != 0:
                return currCont.value
        return None

    def setContrast(self, contrast: Optional[int]):
        if contrast is not None and 0 <= contrast <= 100:
            minCont = ctypes.c_uint()
            currCont = ctypes.c_uint()
            maxCont = ctypes.c_uint()
            hDevices = _win32getPhysicalMonitorsHandles(self.handle)
            for hDevice in hDevices:
                ctypes.windll.dxva2.GetMonitorContrast(hDevice, ctypes.byref(minCont), ctypes.byref(currCont),
                                                       ctypes.byref(maxCont))
                if contrast < minCont.value:
                    contrast = minCont.value
                elif contrast > maxCont.value:
                    contrast = maxCont.value
                ctypes.windll.dxva2.SetMonitorContrast(hDevice, contrast)
                ctypes.windll.dxva2.DestroyPhysicalMonitor(hDevice)

    @property
    def mode(self) -> Optional[DisplayMode]:
        settings = None
        try:
            settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_CURRENT_SETTINGS)
        except:
            try:
                settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_REGISTRY_SETTINGS)
            except:
                pass
        if settings:
            return DisplayMode(settings.PelsWidth, settings.PelsHeight, settings.DisplayFrequency)
        return None

    def setMode(self, mode: Optional[DisplayMode]):
        if mode is not None:
            # devmode = win32api.EnumDisplaySettings(self.name, win32con.ENUM_CURRENT_SETTINGS)
            devmode = pywintypes.DEVMODEType()  # type: ignore[attr-defined]
            devmode.PelsWidth = mode.width
            devmode.PelsHeight = mode.height
            devmode.DisplayFrequency = mode.frequency
            devmode.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
            win32api.ChangeDisplaySettingsEx(self.name, devmode, win32con.CDS_RESET | win32con.CDS_UPDATEREGISTRY)
            # win32api.ChangeDisplaySettingsEx()

    @property
    def defaultMode(self) -> Optional[DisplayMode]:
        settings = win32api.EnumDisplaySettings(self.name, win32con.ENUM_REGISTRY_SETTINGS)
        return DisplayMode(settings.PelsWidth, settings.PelsHeight, settings.DisplayFrequency)

    def setDefaultMode(self):
        defMode = self.defaultMode
        if defMode:
            self.setMode(defMode)

    @property
    def allModes(self) -> list[DisplayMode]:
        modes: List[DisplayMode] = []
        i = 0
        while True:
            try:
                winSettings = win32api.EnumDisplaySettings(self.name, i)
                modes.append(DisplayMode(winSettings.PelsWidth, winSettings.PelsHeight, winSettings.DisplayFrequency))
            except:
                break
            i += 1
        return modes

    @property
    def isPrimary(self) -> bool:
        return bool(self.position == Point(0, 0))

    def setPrimary(self):
        if not self.isPrimary:
            _setPrimary(self.name)

    def turnOn(self):
        # https://stackoverflow.com/questions/16402672/control-screen-with-python
        if self._hasVCPSupport is None:
            self._hasVCPSupport = _win32hasVCPSupport(self.handle)
            self._hasVCPPowerSupport = _win32hasVCPPowerSupport(self.handle)
        if self._hasVCPSupport and self._hasVCPPowerSupport:
            if not self.isOn:
                hDevices = _win32getPhysicalMonitorsHandles(self.handle)
                for hDevice in hDevices:
                    # code and value according to: VESA Monitor Control Command Set (MCCS) standard, version 1.0 and 2.0.
                    ctypes.windll.dxva2.SetVCPFeature(hDevice, 0xD6, 0x01)
                    ctypes.windll.dxva2.DestroyPhysicalMonitor(hDevice)
        else:
            # This produces weird behavior in Win11 (it was OK in Win10)
            if self._isWindows11:
                hwnd = win32gui.GetDesktopWindow()
            else:
                hwnd = win32con.HWND_BROADCAST
            win32gui.SendMessageTimeout(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MONITORPOWER,
                                        -1, win32con.SMTO_ABORTIFHUNG, 100)
            # The code above will not work in modern systems. A mouse move can do the trick (for ALL monitors)
            mx, my = _getMousePos()
            _win32moveMouse(mx + 1, my + 1)
            _win32moveMouse(mx, my)

    def turnOff(self):
        # https://stackoverflow.com/questions/16402672/control-screen-with-python
        if self._hasVCPSupport is None:
            self._hasVCPSupport = _win32hasVCPSupport(self.handle)
            self._hasVCPPowerSupport = _win32hasVCPPowerSupport(self.handle)
        if self._hasVCPSupport and self._hasVCPPowerSupport:
            if self.isOn:
                hDevices = _win32getPhysicalMonitorsHandles(self.handle)
                for hDevice in hDevices:
                    # code and value according to: VESA Monitor Control Command Set (MCCS) standard, version 1.0 and 2.0.
                    ctypes.windll.dxva2.SetVCPFeature(hDevice, 0xD6, 0x05)
                    ctypes.windll.dxva2.DestroyPhysicalMonitor(hDevice)
        else:
            # Using win32con.HWND_BROADCAST produces weird behavior in Win11 (it was OK in Win10)
            # Using any other window handle, weird effects go away, but doesn't work in Win11
            if self._isWindows11:
                hwnd = win32gui.GetDesktopWindow()
                # hinst = win32api.GetModuleHandle(None)
                # wndclass = win32gui.WNDCLASS()
                # wndclass.hInstance = hinst  # type: ignore[misc]
                # wndclass.lpszClassName = "DummyWindowClass"  # type: ignore[misc]
                # myWindowClass = win32gui.RegisterClass(wndclass)
                # hwnd = win32gui.CreateWindowEx(win32con.WS_EX_LEFT,
                #                                myWindowClass,  # type: ignore[misc, arg-type]
                #                                "DummyWindow",
                #                                0,
                #                                0,
                #                                0,
                #                                win32con.CW_USEDEFAULT,
                #                                win32con.CW_USEDEFAULT,
                #                                0,
                #                                0,
                #                                hinst,
                #                                None)
            else:
                hwnd = win32con.HWND_BROADCAST
            win32gui.SendMessageTimeout(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MONITORPOWER,
                                        2, win32con.SMTO_ABORTIFHUNG, 100)

    @property
    def isOn(self) -> Optional[bool]:
        ret: Optional[bool] = None
        if self._hasVCPSupport is None:
            self._hasVCPSupport = _win32hasVCPSupport(self.handle)
            self._hasVCPPowerSupport = _win32hasVCPPowerSupport(self.handle)
        if self._hasVCPSupport and self._hasVCPPowerSupport:
            hDevices = _win32getPhysicalMonitorsHandles(self.handle)
            for hDevice in hDevices:
                # code and value according to: VESA Monitor Control Command Set (MCCS) standard, version 1.0 and 2.0.
                pvct = ctypes.c_uint()
                currValue = ctypes.c_uint()
                maxValue = ctypes.c_uint()
                ctypes.windll.dxva2.GetVCPFeatureAndVCPFeatureReply(hDevice, 0xD6, ctypes.byref(pvct),
                                                                    ctypes.byref(currValue), ctypes.byref(maxValue))
                ret = currValue.value == 1
            _win32destroyPhysicalMonitors(hDevices)
        else:
            # Not working by now (tried with hDevice as well)
            # https://stackoverflow.com/questions/203355/is-there-any-way-to-detect-the-monitor-state-in-windows-on-or-off
            # https://learn.microsoft.com/en-us/windows/win32/power/power-management-functions
            is_working = ctypes.c_bool()
            res = ctypes.windll.kernel32.GetDevicePowerState(self.handle, ctypes.byref(is_working))
            if res:
                ret = bool(is_working.value)
        isSuspended = self.isSuspended
        return (ret and not isSuspended) if isSuspended is not None else ret

    def suspend(self):
        if self._hasVCPSupport is None:
            self._hasVCPSupport = _win32hasVCPSupport(self.handle)
            self._hasVCPPowerSupport = _win32hasVCPPowerSupport(self.handle)
        if self._hasVCPSupport and self._hasVCPPowerSupport:
            hDevices = _win32getPhysicalMonitorsHandles(self.handle)
            for hDevice in hDevices:
                # code and value according to: VESA Monitor Control Command Set (MCCS) standard, version 1.0 and 2.0.
                ctypes.windll.dxva2.SetVCPFeature(hDevice, 0xD6, 0x04)
                ctypes.windll.dxva2.DestroyPhysicalMonitor(hDevice)
        else:
            # This produces weird behavior in Win11 (it was OK in Win10)
            if self._isWindows11:
                hwnd = win32gui.GetDesktopWindow()
            else:
                hwnd = win32con.HWND_BROADCAST
            win32gui.SendMessageTimeout(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MONITORPOWER,
                                        1, win32con.SMTO_ABORTIFHUNG, 100)

    @property
    def isSuspended(self) -> Optional[bool]:
        ret: Optional[bool] = None
        if self._hasVCPSupport is None:
            self._hasVCPSupport = _win32hasVCPSupport(self.handle)
            self._hasVCPPowerSupport = _win32hasVCPPowerSupport(self.handle)
        if self._hasVCPSupport and self._hasVCPPowerSupport:
            hDevices = _win32getPhysicalMonitorsHandles(self.handle)
            for hDevice in hDevices:
                # code and value according to: VESA Monitor Control Command Set (MCCS) standard, version 1.0 and 2.0.
                pvct = ctypes.c_uint()
                currValue = ctypes.c_uint()
                maxValue = ctypes.c_uint()
                ctypes.windll.dxva2.GetVCPFeatureAndVCPFeatureReply(hDevice, 0xD6, ctypes.byref(pvct),
                                                                    ctypes.byref(currValue), ctypes.byref(maxValue))
                ret = currValue.value == 2
                break
            _win32destroyPhysicalMonitors(hDevices)
        return ret

    def attach(self):
        if not self.isAttached:
            # devmode = win32api.EnumDisplaySettings(self.name, win32con.ENUM_REGISTRY_SETTINGS)
            devmode = pywintypes.DEVMODEType()  # type: ignore[attr-defined]
            devmode.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
            win32api.ChangeDisplaySettingsEx(self.name, devmode, win32con.CDS_RESET | win32con.CDS_UPDATEREGISTRY)
            # win32api.ChangeDisplaySettingsEx()
            _findNewHandles()

    def detach(self, permanent: bool = False):
        if self.isAttached:
            # devmode = win32api.EnumDisplaySettings(self.name, win32con.ENUM_CURRENT_SETTINGS)
            devmode = pywintypes.DEVMODEType()  # type: ignore[attr-defined]
            devmode.PelsWidth = 0
            devmode.PelsHeight = 0
            # devmode.Position_x = 0
            # devmode.Position_y = 0
            devmode.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT | win32con.DM_POSITION
            win32api.ChangeDisplaySettingsEx(self.name, devmode, win32con.CDS_RESET | (win32con.CDS_UPDATEREGISTRY if permanent else 0))
            # win32api.ChangeDisplaySettingsEx()
            _findNewHandles()

    @property
    def isAttached(self) -> Optional[bool]:
        # Settings content: http://timgolden.me.uk/pywin32-docs/PyDEVMODE.html
        # This seems to return invalid values (2 instead of 3) in some cases (monitor 1 affected by monitor 3!?!?!?!)
        # dev = win32api.EnumDisplayDevices(self.name, 0, 0)
        # return bool(dev and dev.StateFlags & win32con.DISPLAY_DEVICE_ATTACHED_TO_DESKTOP)
        return self.name in list(_win32getAllMonitorsDict().keys())


def _setPrimary(name: str):
    # https://stackoverflow.com/questions/35814309/winapi-changedisplaysettingsex-does-not-work
    monitors = _win32getAllMonitorsDict()
    if len(monitors.keys()) > 1:
        xOffset = 0
        for monName in monitors.keys():
            if monName == name:
                monInfo = monitors[monName]["monitor"]
                xOffset = abs(monInfo["Monitor"][2] - monInfo["Monitor"][0])
                if monInfo.get("Flags", 0) == win32con.MONITORINFOF_PRIMARY:
                    return
                else:
                    # settings = win32api.EnumDisplaySettings(name, win32con.ENUM_CURRENT_SETTINGS)
                    devmode = pywintypes.DEVMODEType()  # type: ignore[attr-defined]
                    devmode.Position_x = 0
                    devmode.Position_y = 0
                    devmode.Fields = win32con.DM_POSITION
                    flags = win32con.CDS_SET_PRIMARY | win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET
                    win32api.ChangeDisplaySettingsEx(name, devmode, flags)
                    break

        flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET
        for monName in monitors.keys():
            if monName != name:
                monInfo = monitors[monName]["monitor"]
                # settings = win32api.EnumDisplaySettings(monName, win32con.ENUM_CURRENT_SETTINGS)
                devmode = pywintypes.DEVMODEType()  # type: ignore[attr-defined]
                devmode.Position_x = xOffset
                devmode.Position_y = 0
                devmode.Fields = win32con.DM_POSITION
                win32api.ChangeDisplaySettingsEx(monName, devmode, flags)
                xOffset += abs(monInfo["Monitor"][2] - monInfo["Monitor"][0])
        win32api.ChangeDisplaySettingsEx()


def _win32getAllMonitorsDict():
    monitors = {}
    for monitor in win32api.EnumDisplayMonitors():
        hMon = monitor[0].handle
        try:
            monitorInfo = win32api.GetMonitorInfo(hMon)
            monitors[monitorInfo["Device"]] = {"hMon": hMon, "monitor": monitorInfo}
        except:
            pass
    return monitors


def _findNewHandles():
    # https://stackoverflow.com/questions/328851/printing-all-instances-of-a-class
    # Monitor IDs may change after detaching or attaching a monitor. This will try to refresh them in all instances
    stopSearching = True
    while True:
        monitors = win32api.EnumDisplayMonitors()
        otherMonitorInstances = [obj for obj in gc.get_objects() if isinstance(obj, Win32Monitor)]
        for instance in otherMonitorInstances:
            for monitor in monitors:
                instance.handle = None
                instance._sourceAdapterId = None
                instance._sourceId = None
                hMon = monitor[0].handle
                try:
                    monInfo = win32api.GetMonitorInfo(hMon)
                    if instance.name == monInfo.get("Device", ""):
                        instance.handle = hMon
                        break
                except:
                    stopSearching = False
                    break
        if stopSearching:
            break
        time.sleep(0.2)


def _getMonitorInfo(handle: int):
    try:
        monitorInfo = win32api.GetMonitorInfo(handle)
        return monitorInfo
    except:
        pass
    return None


def _win32getPhysicalMonitorsHandles(hMon):
    # https://stackoverflow.com/questions/60580536/changing-monitor-input-source-programmatically

    class _PHYSICAL_MONITOR(ctypes.Structure):
        _fields_ = [('handle', ctypes.wintypes.HANDLE),
                    ('description', ctypes.wintypes.WCHAR * 128)]

    handles = []
    count = ctypes.wintypes.DWORD()
    ret = ctypes.windll.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hMon, ctypes.byref(count))
    if ret and count.value > 0:
        physical_array = (_PHYSICAL_MONITOR * count.value)()
        ret = ctypes.windll.dxva2.GetPhysicalMonitorsFromHMONITOR(hMon, count.value, physical_array)
        if ret:
            for physical in physical_array:
                handles.append(physical.handle)
    return handles


def _win32destroyPhysicalMonitors(hDevices):
    for hDevice in hDevices:
        try:
            ctypes.windll.dxva2.DestroyPhysicalMonitor(hDevice)
        except:
            pass


def _win32moveMouse(x: int, y: int, click: bool = False):
    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, x, y)
    if click:
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)


def _win32hasVCPSupport(handle: int):
    # https://github.com/dot-osk/monitor_ctrl/blob/master/vcp.py
    # https://github.com/newAM/monitorcontrol/blob/main/monitorcontrol/vcp
    res = False
    hDevices = _win32getPhysicalMonitorsHandles(handle)
    for hDevice in hDevices:
        size = ctypes.wintypes.DWORD()
        ret = ctypes.windll.dxva2.GetCapabilitiesStringLength(hDevice, ctypes.byref(size))
        if ret and size.value > 0:
            res = True
            break
    _win32destroyPhysicalMonitors(hDevices)
    return res


def _win32getVCPCapabilities(handle: int):
    # https://github.com/dot-osk/monitor_ctrl/blob/master/vcp.py
    # https://www.ddcutil.com/monitor_notes/
    ret = ""
    hDevices = _win32getPhysicalMonitorsHandles(handle)
    for hDevice in hDevices:
        size = ctypes.wintypes.DWORD()
        res = ctypes.windll.dxva2.GetCapabilitiesStringLength(hDevice, ctypes.byref(size))
        if res and size.value > 0:
            capabilities = (ctypes.c_char * size.value)()
            res = ctypes.windll.dxva2.CapabilitiesRequestAndCapabilitiesReply(hDevice, capabilities, size)
            if res:
                ret = capabilities.value.decode('ASCII')
        break
    _win32destroyPhysicalMonitors(hDevices)
    return ret


def _win32hasVCPPowerSupport(handle: int):
    return "D6(" in _win32getVCPCapabilities(handle)


def _eventLoop(kill: threading.Event, interval: float):
    # https://stackoverflow.com/questions/48720924/python-3-detect-monitor-power-state-in-windows
    # https://wiki.wxpython.org/HookingTheWndProc
    # https://stackoverflow.com/questions/48720924/python-3-detect-monitor-power-state-in-windows
    # https://stackoverflow.com/questions/4273252/detect-inserted-usb-on-windows

    class NotificationWindow:

        def __init__(self):
            hinst = win32api.GetModuleHandle(None)
            wndclass = win32gui.WNDCLASS()
            wndclass.hInstance = hinst  # type: ignore[misc]
            wndclass.lpszClassName = "NotificationLoopWindowClass"  # type: ignore[misc]
            CMPFUNC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p)
            wndproc_pointer = CMPFUNC(self.MyWndProc)
            wndclass.lpfnWndProc = {win32con.WM_POWERBROADCAST: wndproc_pointer}  # type: ignore[misc]

            myWindowClass = win32gui.RegisterClass(wndclass)
            hwnd = win32gui.CreateWindowEx(win32con.WS_EX_LEFT,
                                           myWindowClass,  # type: ignore[misc, arg-type]
                                           "NotificationLoopMsgWindow",
                                           0,
                                           0,
                                           0,
                                           win32con.CW_USEDEFAULT,
                                           win32con.CW_USEDEFAULT,
                                           0,
                                           0,
                                           hinst,
                                           None)
            self.hWnd = hwnd

            # Set the WndProc to our function
            self.oldWndProc = win32gui.SetWindowLong(self.hWnd, win32con.GWL_WNDPROC, self.MyWndProc)

            # Make a dictionary of message names to be used for printing below
            self.msgdict = {}
            for name in dir(win32con):
                if name.startswith("WM_"):
                    value = getattr(win32con, name)
                    self.msgdict[value] = name

        def MyWndProc(self, hWnd, msg, wParam, lParam):

            # Is this necessary since the window is going away?
            # if msg == win32con.WM_DESTROY:
            #     # Set back the WndProc to original function
            #     win32api.SetWindowLong(self.hWnd, win32con.GWL_WNDPROC, self.oldWndProc)
            if msg == win32con.WM_DISPLAYCHANGE:
                print("DISPLAY CHANGE:", self.msgdict.get(msg), hWnd, msg, wParam, lParam)
            else:
                print("OTHER:", self.msgdict.get(msg), hWnd, msg, wParam, lParam)

            return win32gui.CallWindowProc(self.oldWndProc, hWnd, msg, wParam, lParam)

    win = NotificationWindow()
    while not kill.is_set():
        win32gui.PumpWaitingMessages()
        kill.wait(interval)
    win32gui.PostMessage(win.hWnd, win32con.WM_CLOSE, 0, 0)


def _eventLogLoop(kill: threading.Event, interval: float, offset: int = 0):
    # # https://stackoverflow.com/questions/11219213/read-specific-windows-event-log-event
    server = 'localhost'  # name of the target computer to get event logs
    log_type = 'Microsoft-Windows'  # 'Application' / 'System' / 'Microsoft-Windows'
    handle = win32evtlog.OpenEventLog(server, log_type)  # Always returns the length of 'Microsoft-Windows' log
    flags = win32evtlog.EVENTLOG_SEEK_READ | win32evtlog.EVENTLOG_FORWARDS_READ
    total = win32evtlog.GetNumberOfEventLogRecords(handle)
    offset = max(0, total - offset)

    while not kill.is_set():
        if offset < total:
            events = win32evtlog.ReadEventLog(handle, flags, offset)
            for event in events:
                print(event.TimeGenerated, event.EventID, event.SourceName, event.EventCategory, event.EventType, event.StringInserts)
            offset += len(events)

        kill.wait(interval)
        total = win32evtlog.GetNumberOfEventLogRecords(handle)

    win32evtlog.CloseEventLog(handle)

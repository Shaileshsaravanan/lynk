#!/usr/bin/python
# -*- coding: utf-8 -*-
# Incomplete type stubs for pyobjc
# mypy: disable_error_code = no-any-return
from __future__ import annotations

import ctypes
from ctypes import util

import sys
assert sys.platform == "darwin"

import subprocess
import threading

from typing import Optional, List, Union, cast, Tuple

import AppKit
import Quartz
import Quartz.CoreGraphics as CG

from ._main import BaseMonitor, _pointInBox, _getRelativePosition, \
                   DisplayMode, ScreenValue, Box, Rect, Point, Size, Position, Orientation


def _getAllMonitors() -> list[MacOSMonitor]:
    monitors = []
    v, ids, cnt = CG.CGGetOnlineDisplayList(10, None, None)  # --> How to get display name from this?
    for displayId in ids:
        monitors.append(MacOSMonitor(displayId))
    return monitors


def _getAllMonitorsDict() -> dict[str, ScreenValue]:
    result: dict[str, ScreenValue] = {}
    for mon in _NSgetAllMonitors():
        screen, desc, displayId, scrName = mon

        try:
            name = screen.localizedName()
        except:
            # In older macOS, screen doesn't have localizedName() method
            name = "Display" + "_" + str(displayId)
        is_primary = Quartz.CGDisplayIsMain(displayId) == 1
        x, y, w, h = int(screen.frame().origin.x), int(screen.frame().origin.y), int(screen.frame().size.width), int(screen.frame().size.height)
        wa = screen.visibleFrame()
        wx, wy, wr, wb = int(wa.origin.x), int(wa.origin.y), int(wa.size.width), int(wa.size.height)
        scale = _scale(displayId)
        dpi = desc[Quartz.NSDeviceResolution].sizeValue()
        dpiX, dpiY = int(dpi.width), int(dpi.height)
        rot = Orientation(int(Quartz.CGDisplayRotation(displayId) / 90))
        freq = Quartz.CGDisplayModeGetRefreshRate(Quartz.CGDisplayCopyDisplayMode(displayId))
        depth = Quartz.CGDisplayBitsPerPixel(displayId)

        result[scrName] = {
            'system_name': name,
            'id': displayId,
            'is_primary': is_primary,
            'position': Point(x, y),
            'size': Size(w, h),
            'workarea': Rect(wx, wy, wr, wb),
            'scale': scale,
            'dpi': (dpiX, dpiY),
            'orientation': rot,
            'frequency': freq,
            'colordepth': depth
        }
    return result


def _getMonitorsCount() -> int:
    v, ids, cnt = CG.CGGetOnlineDisplayList(10, None, None)
    return cnt


def _findMonitor(x: int, y: int) -> List[MacOSMonitor]:
    v, ids, cnt = CG.CGGetDisplaysWithPoint((x, y), 10, None, None)
    return [MacOSMonitor(displayId) for displayId in ids]


def _getPrimary() -> MacOSMonitor:
    return MacOSMonitor()


def _arrangeMonitors(arrangement: dict[str, dict[str, Optional[Union[str, int, Position, Point, Size]]]]):

    monitors = _NSgetAllMonitorsDict()
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

    newPos: dict[str, dict[str, int]] = {setAsPrimary: {"x": 0, "y": 0}}
    commitChanges = True
    ret, configRef = Quartz.CGBeginDisplayConfiguration(None)
    if ret != 0:
        return

    x, y = 0, 0
    ret = Quartz.CGConfigureDisplayOrigin(configRef, monitors[setAsPrimary]["displayId"], x, y)
    if ret != 0:
        Quartz.CGCancelDisplayConfiguration(configRef)
        return

    for monName in arrangement.keys():

        relativePos: Union[Position, int, Point, Tuple[int, int]] = arrangement[monName]["relativePos"]

        if monName != setAsPrimary:

            if isinstance(relativePos, Position) or isinstance(relativePos, int):

                relativeTo = str(arrangement[monName]["relativeTo"])

                frame = monitors[monName]["screen"].frame()
                targetMon = {"relativePos": relativePos, "relativeTo": relativeTo,
                             "position": Point(frame.origin.x, frame.origin.y),
                             "size": Size(frame.size.width, frame.size.height)}

                frame = monitors[relativeTo]["screen"].frame()
                if relativeTo in newPos.keys():
                    relX, relY = newPos[relativeTo]["x"], newPos[relativeTo]["y"]
                else:
                    relX, relY = x, y
                relMon = {"position": Point(relX, relY), "size": Size(frame.size.width, frame.size.height)}

                x, y = _getRelativePosition(targetMon, relMon)

            else:
                x, y = relativePos

            ret = Quartz.CGConfigureDisplayOrigin(configRef, monitors[monName]["displayId"], x, y)
            newPos[monName] = {"x": x, "y": y}
            if ret != 0:
                commitChanges = False
                break

    if commitChanges:
        Quartz.CGCompleteDisplayConfiguration(configRef, Quartz.kCGConfigurePermanently)
    else:
        Quartz.CGCancelDisplayConfiguration(configRef)


def _getMousePos(flipValues: bool = False) -> Point:
    """
    Get the current (x, y) coordinates of the mouse pointer on screen, in pixels

    Notice in AppKit the origin (0, 0) is bottom left (unflipped), which may differ to coordinates obtained
    using AppScript or CoreGraphics (flipped). To manage this, use 'flipValues' accordingly.

    :param flipValues: set to ''True'' to convert coordinates to origin (0, 0) at upper left corner
    :return: Point struct
    """
    # https://stackoverflow.com/questions/3698635/getting-cursor-position-in-python/24567802
    mp = Quartz.NSEvent.mouseLocation()
    x, y = int(mp.x), int(mp.y)
    if flipValues:
        screens = AppKit.NSScreen.screens()
        for screen in screens:
            frame = screen.frame()
            sx, sy, sw, sh = int(frame.origin.x), int(frame.origin.y), int(frame.size.width), int(frame.size.height)
            if _pointInBox(x, y, sx, sy, sw, sh):
                y = (-1 if y < 0 else 1) * (int(sh) - abs(y))
                break
    return Point(x, y)


class MacOSMonitor(BaseMonitor):

    def __init__(self, handle: Optional[int] = None):
        """
        Class to access all methods and functions to get info and manage monitors plugged to the system.

        This class is not meant to be directly instantiated. Instead, use convenience functions like getAllMonitors(),
        getPrimary() or findMonitor(x, y).

        It can raise ValueError exception in case provided handle is not valid
        """
        if not handle:
            self.screen = AppKit.NSScreen.mainScreen()
            self.handle = Quartz.CGMainDisplayID()
        else:
            self.screen = None
            self.handle = handle
            for screen in AppKit.NSScreen.screens():
                desc = screen.deviceDescription()
                displayId = desc['NSScreenNumber']  # Quartz.NSScreenNumber seems to be wrong
                if handle == displayId:
                    self.screen = screen
                    break
        if self.screen is not None:
            self.name = _getName(self.handle, self.screen)
            self._ds: Optional[ctypes.CDLL] = None
            self._useDS = True
            self._cd: Optional[ctypes.CDLL] = None
            self._useCD = True
            self._iokit: Optional[ctypes.CDLL] = None
            self._useIOBrightness = True
            self._useIOOrientation = True
            self._cf: Optional[ctypes.CDLL] = None
            self._ioservice: Optional[int] = None
            # In some versions / systems, IOKit may fail
            # v = platform.mac_ver()[0].split(".")
            # self._ver = float(v[0] + "." + v[1])
        else:
            raise ValueError

    @property
    def size(self, ) -> Optional[Size]:
        size = self.screen.frame().size
        res = Size(int(size.width), int(size.height))
        return res

    @property
    def workarea(self) -> Optional[Rect]:
        wa = self.screen.visibleFrame()
        wx, wy, wr, wb = int(wa.origin.x), int(wa.origin.y), int(wa.size.width), int(wa.size.height)
        res = Rect(wx, wy, wr, wb)
        return res

    @property
    def position(self) -> Optional[Point]:
        origin = self.screen.frame().origin
        res = Point(int(origin.x), int(origin.y))
        return res

    def setPosition(self, relativePos: Union[int, Position, Point, Tuple[int, int]], relativeTo: Optional[str]):
        # https://apple.stackexchange.com/questions/249447/change-display-arrangement-in-os-x-macos-programmatically
        arrangement: dict[str, dict[str, Optional[Union[str, int, Position, Point, Size]]]] = {}
        monitors = _NSgetAllMonitorsDict()
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
            xOffset = self.screen.frame().size.width

            for monName in monKeys:
                relPos = Point(xOffset, 0)
                arrangement[monName] = {"relativePos": relPos, "relativeTo": None}
                xOffset += monitors[monName]["screen"].frame().size.width

        else:

            for monName in monKeys:
                if monName == self.name:
                    relPos = relativePos
                    relTo = relativeTo
                else:
                    monitor = monitors[monName]["screen"]
                    x, y = monitor.frame().origin
                    if (x, y) == (0, 0):
                        relPos = Position.PRIMARY
                    else:
                        relPos = Point(x, y)
                    relTo = None
                arrangement[monName] = {"relativePos": relPos, "relativeTo": relTo}

        _arrangeMonitors(arrangement)

    @property
    def box(self) -> Optional[Box]:
        frame = self.screen.frame()
        res = Box(int(frame.origin.x), int(frame.origin.y), int(frame.size.width), int(frame.size.height))
        return res

    @property
    def rect(self) -> Optional[Rect]:
        frame = self.screen.frame()
        res = Rect(int(frame.origin.x), int(frame.origin.y),
                   int(frame.origin.x) + int(frame.size.width), int(frame.origin.y) + int(frame.size.height))
        return res

    @property
    def scale(self) -> Optional[Tuple[float, float]]:
        return _scale(self.handle)

    def setScale(self, scale: Tuple[float, float], applyGlobally: bool = True):
        # https://www.eizoglobal.com/support/compatibility/dpi_scaling_settings_mac_os_x/

        if scale is not None and isinstance(scale, tuple) and scale[0] >= 100 and scale[1] >= 100:

            scaleX, scaleY = scale

            defaultMode = self.defaultMode
            if defaultMode:
                defaultHeight = defaultMode.height  # Taking default mode height as 100% scale
                currMode = self.mode
                if currMode:
                    currHeight = currMode.height
                    if currHeight:
                        if defaultHeight / currHeight == scaleY:
                            return
                    currRate = currMode.frequency
                else:
                    return
            else:
                return

            def filterValue(itemIn):
                valueIn, freqIn, modeIn = itemIn
                return valueIn, freqIn

            # Retrieve all modes and their size ratio vs. default
            modes = []
            for mode in _CGgetAllModes(self.handle):
                modeHeight = Quartz.CGDisplayModeGetHeight(mode)
                ratio = int((defaultHeight / modeHeight) * 100)
                freq = Quartz.CGDisplayModeGetRefreshRate(mode)
                modes.append((ratio, freq, mode))
            modes.sort(key=filterValue)
            ratio, freq, targetMode = modes[len(modes) - 1]

            # Find modes with target ratio and their refresh rate
            if ratio > scaleY:
                targetRatio = 0
                for item in modes:
                    ratio, freq, mode = item
                    if ratio >= scaleY:
                        targetMode = mode
                        if targetRatio == 0:
                            targetRatio = ratio
                        if ratio == targetRatio:
                            if freq >= currRate:
                                break
                        else:
                            break

            if targetMode != Quartz.CGDisplayCopyDisplayMode(self.handle):
                CG.CGDisplaySetDisplayMode(self.handle, targetMode, None)

    @property
    def dpi(self) -> Optional[Tuple[float, float]]:
        desc = self.screen.deviceDescription()
        dpi = desc[Quartz.NSDeviceResolution].sizeValue()
        dpiX, dpiY = int(dpi.width), int(dpi.height)
        return dpiX, dpiY

    @property
    def orientation(self) -> Optional[Union[int, Orientation]]:
        orientation = int(Quartz.CGDisplayRotation(self.handle) / 90)
        if orientation in (Orientation.NORMAL, Orientation.INVERTED, Orientation.LEFT, Orientation.RIGHT):
            return Orientation(orientation)
        return None

    def setOrientation(self, orientation: Optional[Union[int, Orientation]]):
        if (self._useIOOrientation
                and orientation and orientation in (Orientation.NORMAL, Orientation.INVERTED, Orientation.LEFT, Orientation.RIGHT)):
            if self._iokit is None:
                self._iokit, self._cf, self._ioservice = _loadIOKit(self.handle)
            if self._iokit is not None and self._ioservice is not None:
                swapAxes = 0x10
                invertX = 0x20
                invertY = 0x40
                angleCodes = {
                    0: 0,
                    90: (swapAxes | invertX) << 16,
                    180: (invertX | invertY) << 16,
                    270: (swapAxes | invertY) << 16,
                }
                rotateCode = 0x400
                options = rotateCode | angleCodes[(orientation * 90) % 360]

                try:
                    ret = self._iokit.IOServiceRequestProbe(self._ioservice, options)
                except:
                    ret = 1
                if ret != 0:
                    self._useIOOrientation = False
            else:
                self._useIOBrightness = False
                self._useIOOrientation = False

    @property
    def frequency(self) -> Optional[float]:
        freq = Quartz.CGDisplayModeGetRefreshRate(Quartz.CGDisplayCopyDisplayMode(self.handle))
        return freq

    @property
    def colordepth(self) -> Optional[int]:
        depth = Quartz.CGDisplayBitsPerPixel(self.handle)
        return depth

    @property
    def brightness(self) -> Optional[int]:
        res = None
        ret = 1
        if self._useDS:
            if self._ds is None:
                self._ds = _loadDisplayServices()
            if self._ds is not None:
                value = ctypes.c_float()
                try:
                    ret = self._ds.DisplayServicesGetBrightness(self.handle, ctypes.byref(value))
                except:
                    ret = 1
                if ret == 0:
                    res = value.value
                else:
                    self._useDS = False
            else:
                self._useDS = False
        if ret != 0 and self._useCD:
            if self._cd is None:
                self._cd = _loadCoreDisplay()
            if self._cd is not None:
                value = ctypes.c_double()
                try:
                    ret = self._cd.CoreDisplay_Display_GetUserBrightness(self.handle, ctypes.byref(value))
                except:
                    ret = 1
                if ret == 0:
                    res = value.value
                else:
                    self._useCD = False
            else:
                self._useCD = False
        if ret != 0 and self._useIOBrightness:  # and self._ver > 10.15:
            if self._iokit is None:
                self._iokit, self._cf, self._ioservice = _loadIOKit(self.handle)
            if self._iokit is not None and self._cf is not None and self._ioservice is not None:
                kDisplayBrightnessKey = self._cf.CFStringCreateWithCString(None, b"brightness", 0)
                value = ctypes.c_float()
                try:
                    ret = self._iokit.IODisplayGetFloatParameter(self._ioservice, 0, kDisplayBrightnessKey, ctypes.byref(value))
                except:
                    ret = 1
                if ret == 0:
                    res = value.value
                else:
                    self._useIOBrightness = False
            else:
                self._useIOBrightness = False
                self._useIOOrientation = False
        if res is not None:
            return int(res * 100)
        return None

    def setBrightness(self, brightness: Optional[int]):
        # https://stackoverflow.com/questions/46885603/is-there-a-programmatic-way-to-check-if-brightness-is-at-max-or-min-value-on-osx
        if brightness is not None and 0 < brightness < 100:
            ret = 1
            if self._useDS:
                if self._ds is None:
                    self._ds = _loadDisplayServices()
                if self._ds is not None:
                    value = ctypes.c_float(brightness / 100)
                    try:
                        ret = 0
                        if self._ds.DisplayServicesCanChangeBrightness(self.handle):
                            ret = self._ds.DisplayServicesSetBrightness(self.handle, value)
                    except:
                        ret = 1
                    if ret != 0:
                        self._useDS = False
                else:
                    self._useDS = False
            if ret != 0 and self._useDS:
                if self._cd is None:
                    self._cd = _loadCoreDisplay()
                if self._cd is not None:
                    value = ctypes.c_double(brightness / 100)
                    try:
                        ret = self._cd.CoreDisplay_Display_SetUserBrightness(self.handle, value)
                    except:
                        ret = 1
                    if ret != 0:
                        self._useCD = False
                else:
                    self._useCD = False
            if ret != 0 and self._useIOBrightness:
                if self._iokit is None:
                    self._iokit, self._cf, self._ioservice = _loadIOKit(self.handle)
                if self._iokit is not None and self._cf is not None and self._ioservice is not None:
                    kDisplayBrightnessKey = self._cf.CFStringCreateWithCString(None, b"brightness", 0)
                    value = ctypes.c_float(brightness / 100)
                    try:
                        ret = self._iokit.IODisplaySetFloatParameter(self._ioservice, 0, kDisplayBrightnessKey, value)
                    except:
                        ret = 1
                    if ret != 0:
                        self._useIOBrightness = False
                else:
                    self._useIOBrightness = False

    @property
    def contrast(self) -> Optional[int]:
        # https://searchcode.com/file/2207916/pyobjc-framework-Quartz/PyObjCTest/test_cgdirectdisplay.py/
        contrast = None
        try:
            ret, redMin, redMax, redGamma, greenMin, greenMax, greenGamma, blueMin, blueMax, blueGamma = (
                CG.CGGetDisplayTransferByFormula(self.handle, None, None, None, None, None, None, None, None, None))
            if ret == 0:
                contrast = int((float(redGamma) + float(greenGamma) + float(blueGamma)) / 3 * 100)
        except:
            pass
        return contrast

    def setContrast(self, contrast: Optional[int]):
        # https://searchcode.com/file/2207916/pyobjc-framework-Quartz/PyObjCTest/test_cgdirectdisplay.py/
        if contrast is not None and 0 <= contrast <= 100:
            ret, redMin, redMax, redGamma, greenMin, greenMax, greenGamma, blueMin, blueMax, blueGamma = (
                CG.CGGetDisplayTransferByFormula(self.handle, None, None, None, None, None, None, None, None, None))
            if ret == 0:
                newRedGamma = contrast / 100
                if newRedGamma < redMin:
                    newRedGamma = redMin
                elif newRedGamma > redMax:
                    newRedGamma = redMax
                newGreenGamma = contrast / 100
                if newGreenGamma < greenMin:
                    newGreenGamma = greenMin
                elif newGreenGamma > greenMax:
                    newGreenGamma = greenMax
                newBlueGamma = contrast / 100
                if newBlueGamma < blueMin:
                    newBlueGamma = blueMin
                elif newBlueGamma > blueMax:
                    newBlueGamma = blueMax
                ret = CG.CGSetDisplayTransferByFormula(self.handle,
                                                       redMin, redMax, newRedGamma,
                                                       greenMin, greenMax, newGreenGamma,
                                                       blueMin, blueMax, newBlueGamma
                                                       )

    @property
    def mode(self) -> Optional[DisplayMode]:
        mode = Quartz.CGDisplayCopyDisplayMode(self.handle)
        w = Quartz.CGDisplayModeGetWidth(mode)
        h = Quartz.CGDisplayModeGetHeight(mode)
        r = Quartz.CGDisplayModeGetRefreshRate(mode)
        return DisplayMode(w, h, r)

    def setMode(self, mode: Optional[DisplayMode]):
        # https://stackoverflow.com/questions/10596489/programmatically-change-resolution-os-x
        # https://searchcode.com/file/2207916/pyobjc-framework-Quartz/PyObjCTest/test_cgdirectdisplay.py/
        if mode is not None:
            # bestMode, ret = CG.CGDisplayBestModeForParametersAndRefreshRate(self.handle, self.colordepth,
            #                                                                 mode.width, mode.height, mode.frequency,
            #                                                                 None)
            mw, mh, mr = mode.width, mode.height, mode.frequency
            allModes = _CGgetAllModes(self.handle)
            for m in allModes:
                w = Quartz.CGDisplayModeGetWidth(m)
                h = Quartz.CGDisplayModeGetHeight(m)
                r = Quartz.CGDisplayModeGetRefreshRate(m)
                if w == mw and h == mh and r == mr:
                    CG.CGDisplaySetDisplayMode(self.handle, m, None)
                    break

    @property
    def defaultMode(self) -> Optional[DisplayMode]:
        res: Optional[DisplayMode] = None
        modes = _CGgetAllModes(self.handle)
        for mode in modes:
            if bin(Quartz.CGDisplayModeGetIOFlags(mode))[-3] == '1':
                w = Quartz.CGDisplayModeGetWidth(mode)
                h = Quartz.CGDisplayModeGetHeight(mode)
                r = Quartz.CGDisplayModeGetRefreshRate(mode)
                res = DisplayMode(w, h, r)
                break
        return res

    def setDefaultMode(self):
        modes = _CGgetAllModes(self.handle)
        for mode in modes:
            if bin(Quartz.CGDisplayModeGetIOFlags(mode))[-3] == '1':
                CG.CGDisplaySetDisplayMode(self.handle, mode, None)
                break

    @property
    def allModes(self) -> List[DisplayMode]:
        modes: List[DisplayMode] = []
        for mode in _CGgetAllModes(self.handle):
            w = Quartz.CGDisplayModeGetWidth(mode)
            h = Quartz.CGDisplayModeGetHeight(mode)
            r = Quartz.CGDisplayModeGetRefreshRate(mode)
            modes.append(DisplayMode(w, h, r))
        modesSet = set(modes)
        return list(modesSet)

    @property
    def isPrimary(self):
        return self.handle == Quartz.CGMainDisplayID()

    def setPrimary(self):
        # https://stackoverflow.com/questions/13722508/change-main-monitor-on-mac-programmatically#:~:text=To%20change%20the%20secondary%20monitor%20to%20be%20the,%28%29.%20A%20full%20sample%20can%20be%20found%20Here
        if not self.isPrimary:
            self.setPosition(Position.PRIMARY, "")

    def turnOn(self):
        cmd = "caffeinate -u -t 2"
        try:
            _ = subprocess.run(cmd, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1)
        except:
            pass

    def turnOff(self):
        self.suspend()

    @property
    def isOn(self) -> Optional[bool]:
        return bool(CG.CGDisplayIsActive(self.handle) == 1)

    def suspend(self):
        # Also injecting: Control–Shift–Media_Eject
        cmd = "pmset displaysleepnow"
        try:
            _ = subprocess.run(cmd, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1)
        except:
            pass

    @property
    def isSuspended(self) -> Optional[bool]:
        return bool(CG.CGDisplayIsAsleep(self.handle) == 1)

    def attach(self):
        pass

    def detach(self, permanent: bool = False):
        # Maybe manipulating brightness, contrast, position, size and/or mode?
        pass

    @property
    def isAttached(self) -> Optional[bool]:
        return bool(CG.CGDisplayIsOnline(self.handle) == 1)


def _getName(displayId: int, screen: Optional[AppKit.NSScreen] = None):
    if not screen:
        for scr in AppKit.NSScreen.screens():
            desc = scr.deviceDescription()
            if desc['NSScreenNumber'] == displayId:
                screen = scr
                break
    try:
        scrName = cast(AppKit.NSScreen, screen).localizedName() + "_" + str(displayId)
    except:
        # In older macOS, screen doesn't have localizedName() method
        scrName = "Display" + "_" + str(displayId)
    return scrName


def _scale(handle):
    # value = float(screen.backingScaleFactor() * 100)
    value = 0.0
    dh = 0
    for mode in _CGgetAllModes(handle):
        if bin(Quartz.CGDisplayModeGetIOFlags(mode))[-3] == '1':
            dh = Quartz.CGDisplayModeGetHeight(mode)
            break
    currMode = Quartz.CGDisplayCopyDisplayMode(handle)
    ch = Quartz.CGDisplayModeGetHeight(currMode)
    if ch:
        value = float(int((dh / ch) * 100))
    scale = (value, value)
    return scale


def _CGgetAllModes(handle, showHiDpi: bool = True):
    # Test this with all combinations:
    flags = {}
    if showHiDpi:
        flags[Quartz.kCGDisplayShowDuplicateLowResolutionModes] = Quartz.kCFBooleanTrue
    return Quartz.CGDisplayCopyAllDisplayModes(handle, flags)


def _NSgetAllMonitors():
    monitors = []
    screens = AppKit.NSScreen.screens()
    for screen in screens:
        desc = screen.deviceDescription()
        displayId = desc['NSScreenNumber']  # Quartz.NSScreenNumber seems to be wrong
        scrName = _getName(displayId, screen)
        monitors.append([screen, desc, displayId, scrName])
    return monitors


def _NSgetAllMonitorsDict():
    monitors = {}
    screens = AppKit.NSScreen.screens()
    for screen in screens:
        desc = screen.deviceDescription()
        displayId = desc['NSScreenNumber']  # Quartz.NSScreenNumber seems to be wrong
        scrName = _getName(displayId, screen)
        monitors[scrName] = {"screen": screen, "desc": desc, "displayId": displayId}
    return monitors


# https://stackoverflow.com/questions/30816183/iokit-ioservicegetmatchingservices-broken-under-python3
# https://stackoverflow.com/questions/65150131/iodisplayconnect-is-gone-in-big-sur-of-apple-silicon-what-is-the-replacement
# https://alexdelorenzo.dev/programming/2018/08/16/reverse_engineering_private_apple_apis

def _loadDisplayServices():
    # Display Services Framework can be used in modern systems. It takes A LOT to load
    try:
        ds: ctypes.CDLL = ctypes.cdll.LoadLibrary('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
    except:
        return None
    return ds


def _loadCoreDisplay():
    # Another option is to use Core Display Services
    try:
        lib = ctypes.util.find_library("CoreDisplay")
        if not lib:
            return None
        cd: ctypes.CDLL = ctypes.cdll.LoadLibrary(lib)
        cd.CoreDisplay_Display_SetUserBrightness.argtypes = [ctypes.c_int, ctypes.c_double]
        cd.CoreDisplay_Display_GetUserBrightness.argtypes = [ctypes.c_int, ctypes.c_void_p]
    except:
        return None
    return cd


def _loadIOKit(displayID = Quartz.CGMainDisplayID()):
    # In other systems, we can try to use IOKit
    # https://github.com/nriley/brightness/blob/master/brightness.c
    # https://stackoverflow.com/questions/22841741/calling-functions-with-arguments-from-corefoundation-using-ctypes

    try:
        class _CFString(ctypes.Structure):
            pass

        CFStringRef = ctypes.POINTER(_CFString)

        lib = ctypes.util.find_library("CoreFoundation")
        if not lib:
            return None, None, None
        CF: ctypes.CDLL = ctypes.cdll.LoadLibrary(lib)
        CF.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        CF.CFStringCreateWithCString.restype = CFStringRef
        CF.CFRelease.argtypes = [ctypes.c_void_p]

        lib = ctypes.util.find_library('IOKit')
        if not lib:
            return None, None, None
        iokit: ctypes.CDLL = ctypes.cdll.LoadLibrary(lib)
        iokit.IODisplayGetFloatParameter.argtypes = [ctypes.c_void_p, ctypes.c_uint, CFStringRef, ctypes.POINTER(ctypes.c_float)]
        iokit.IODisplayGetFloatParameter.restype = ctypes.c_int
        iokit.IODisplaySetFloatParameter.argtypes = [ctypes.c_void_p, ctypes.c_uint, CFStringRef, ctypes.c_float]
        iokit.IODisplaySetFloatParameter.restype = ctypes.c_int
        iokit.IOServiceRequestProbe.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        iokit.IOServiceRequestProbe.restype = ctypes.c_int

        try:
            service: int = Quartz.CGDisplayIOServicePort(displayID)
        except:
            service = 0

        # Check if this works in an actual macOS (preferably in several versions)
        if not service:
            # CGDisplayIOServicePort may not work in all versions/architectures

            iokit.IOServiceMatching.restype = ctypes.c_void_p
            iokit.IOServiceGetMatchingServices.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            iokit.IOServiceGetMatchingServices.restype = ctypes.c_void_p
            iokit.IODisplayCreateInfoDictionary.restype = ctypes.c_void_p

            CF.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, CFStringRef]
            CF.CFDictionaryGetValue.restype = ctypes.c_void_p

            kIOMasterPortDefault = ctypes.c_void_p.in_dll(iokit, "kIOMasterPortDefault")

            iterator = ctypes.c_void_p()
            ret = iokit.IOServiceGetMatchingServices(
                kIOMasterPortDefault,
                iokit.IOServiceMatching(b'IODisplayConnect'),
                ctypes.byref(iterator)
            )

            kIODisplayNoProductName = 0x00000400
            kDisplaySerialNumber = CF.CFStringCreateWithCString(None, b"DisplaySerialNumber", 0)
            while True:
                service = iokit.IOIteratorNext(iterator)
                if not service:
                    break
                info = iokit.IODisplayCreateInfoDictionary(service, kIODisplayNoProductName)
                serialNumber = CF.CFDictionaryGetValue(info, kDisplaySerialNumber)
                CF.CFRelease(info)
                if serialNumber == Quartz.CGDisplaySerialNumber(displayID):
                    break

        if service:
            return iokit, CF, service
    except:
        pass

    return None, None, None


def _eventLoop(kill: threading.Event, interval: float):

    def reconfig(displayId, flags, userInfo):
        '''
        FLAGS:
        beginConfigurationFlag:
            The display configuration is about to change.
        movedFlag:
            The location of the upper-left corner of the display in the global display coordinate space has changed.
        setMainFlag:
            The display is now the main display.
        setModeFlag:
            The display mode has changed.
        addFlag:
            The display has been added to the active display list.
        removeFlag:
            The display has been removed from the active display list.
        enabledFlag:
            The display has been enabled.
        disabledFlag:
            The display has been disabled.
        mirrorFlag:
            The display is now mirroring another display.
        unMirrorFlag:
            The display is no longer mirroring another display.
        desktopShapeChangedFlag
        '''
        print("RECONFIG", displayId, flags, userInfo)

    Quartz.CGDisplayRegisterReconfigurationCallback(reconfig, None)
    while not kill.is_set():
        kill.wait(interval)
    Quartz.CGDisplayRemoveReconfigurationCallback(reconfig, None)

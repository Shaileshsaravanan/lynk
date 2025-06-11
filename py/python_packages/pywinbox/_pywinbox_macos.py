#!/usr/bin/python
# -*- coding: utf-8 -*-
# Incomplete type stubs for pyobjc
# mypy: disable_error_code = no-any-return
from __future__ import annotations

import sys

assert sys.platform == "darwin"

import subprocess
from typing import NamedTuple, Union, Optional, cast

import AppKit

from ._main import Box


class _macOSNSHandle(NamedTuple):
    isNSHandle: bool
    window: AppKit.NSWindow


class _macOSCGHandle(NamedTuple):
    isNSHandle: bool
    appName: str
    windowTitle: str


def _getHandle(handle) -> Optional[Union[_macOSCGHandle, _macOSNSHandle]]:
    newHandle = None
    if isinstance(handle, tuple):
        app, window = handle
        if isinstance(app, str) and isinstance(window, str):
            newHandle = _macOSCGHandle(False, app, window)
    elif isinstance(handle, AppKit.NSWindow):
        newHandle = _macOSNSHandle(True, handle)
    return newHandle


def _checkPermissions(activate: bool = False) -> bool:
    """
    macOS ONLY: Check Apple Script permissions for current script/app and, optionally, shows a
    warning dialog and opens security preferences

    :param activate: If ''True'' and if permissions are not granted, shows a dialog and opens security preferences.
                     Defaults to ''False''
    :return: ''True'' if permissions are already granted or platform is not macOS
    """
    # https://stackoverflow.com/questions/26591560/how-to-grant-applescript-permissions-through-applescript
    if activate:
        cmd = """tell application "System Events"
                    set UI_enabled to UI elements enabled
                end tell
                if UI_enabled is false then
                    display dialog "This script requires Accessibility permissions" & return & return & "You can activate GUI Scripting by selecting the checkbox Enable access for assistive devices in the Security and Privacy > Accessibility preferences" with icon 1 buttons {"Ok"} default button 1
                    tell application "System Preferences"
                        activate
                        set current pane to pane id "com.apple.preference.security"
                    end tell
                end if
                return UI_enabled"""
    else:
        cmd = """tell application "System Events"
                    set UI_enabled to UI elements enabled
                end tell
                return UI_enabled"""
    proc = subprocess.Popen(['osascript'],  stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf8')
    ret, err = proc.communicate(cmd)
    ret = ret.replace("\n", "")
    return ret == "true"


def _getWindowBox(handle: Union[_macOSNSHandle, _macOSCGHandle], flipValues: bool = False):
    if handle.isNSHandle:
        handle = cast(_macOSNSHandle, handle)
        return _NSgetWindowBox(handle.window, flipValues)
    else:
        handle = cast(_macOSCGHandle, handle)
        return _CGgetWindowBox(handle.appName, handle.windowTitle)


def _moveResizeWindow(handle: Union[_macOSNSHandle, _macOSCGHandle], newBox: Box, flipValues: bool = False):
    if handle.isNSHandle:
        handle = cast(_macOSNSHandle, handle)
        _NSmoveResizeTo(handle.window, newBox, flipValues)
    else:
        handle = cast(_macOSCGHandle, handle)
        _CGmoveResizeTo(handle.appName, handle.windowTitle, newBox)


def _CGgetWindowBox(appName: str, title: str) -> Box:
    if not _checkPermissions(True) or not appName or not title:
        return Box(0, 0, 0, 0)

    cmd = """on run {arg1, arg2}
                set procName to arg1
                set winName to arg2
                set appBounds to {{0, 0}, {0, 0}}
                try
                    tell application "System Events" to tell application process procName
                        set appBounds to {position, size} of window winName
                    end tell
                end try
                return appBounds
            end run"""
    proc = subprocess.Popen(['osascript', '-', appName, title],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf8')
    ret, err = proc.communicate(cmd)
    if not ret:
        ret = "0, 0, 0, 0"
    w = ret.replace("\n", "").strip().split(", ")
    return Box(int(w[0]), int(w[1]), int(w[2]), int(w[3]))


def _CGmoveResizeTo(appName: str, title: str, newBox: Box):
    if not _checkPermissions(True) or not appName or not title:
        return False

    cmd = """on run {arg1, arg2, arg3, arg4, arg5, arg6}
                set appName to arg1 as string
                set winName to arg2 as string
                set posX to arg3 as integer
                set posY to arg4 as integer
                set sizeW to arg5 as integer
                set sizeH to arg6 as integer
                try
                    tell application "System Events" to tell application process appName
                        set position of window winName to {posX, posY}
                        set size of window winName to {sizeW, sizeH}
                    end tell
                end try
            end run"""
    proc = subprocess.Popen(['osascript', '-', appName, title,
                             str(newBox.left), str(newBox.top), str(newBox.width), str(newBox.height)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding='utf8')
    _, _ = proc.communicate(cmd)


def _flipTop(window: AppKit.NSWindow, box: Box) -> int:
    # https://www.krizka.net/2010/04/20/converting-between-kcgwindowbounds-and-nswindowframe/
    # https://stackoverflow.com/questions/6901651/mac-os-x-cocoa-flipping-y-coordinate-in-global-screen-coordinate-space
    screenSize = window.screen().frame().size
    boundY = screenSize.height - (box.top + box.height)
    # boundY = box.top - box.height
    return boundY


def _unflipTop(window: AppKit.NSWindow, box: Box) -> int:
    # nsY = box.top + box.height
    nsY = _flipTop(window, box)
    return nsY


def _NSgetWindowBox(window: AppKit.NSWindow, flipValues: bool = False) -> Box:
    frame = window.frame()
    x = int(frame.origin.x)
    y = int(frame.origin.y)
    w = int(frame.size.width)
    h = int(frame.size.height)
    if flipValues:
        y = _flipTop(window, Box(x, y, w, h))
    return Box(x, y, w, h)


def _NSmoveResizeTo(window: AppKit.NSWindow, newBox: Box, flipValues: bool = False):
    newTop = newBox.top
    if flipValues:
        newTop = _unflipTop(window, newBox)
    window.setFrame_display_animate_(AppKit.NSMakeRect(newBox.left, newTop, newBox.width, newBox.height), True, True)

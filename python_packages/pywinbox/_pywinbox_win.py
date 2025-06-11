#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys

assert sys.platform == "win32"

from typing import Union, Optional

import ctypes
import win32gui

from ._main import Box


# Thanks to poipoiPIO (https://github.com/poipoiPIO) for his HELP!!!
try:
    dpiAware = ctypes.windll.user32.GetAwarenessFromDpiAwarenessContext(ctypes.windll.user32.GetThreadDpiAwarenessContext())
except AttributeError:  # Windows server does not implement GetAwarenessFromDpiAwarenessContext
    dpiAware = 0

if dpiAware == 0:
    # It seems that this can't be invoked twice. Setting it to 1 for apps having 0 (unaware) may have less impact
    ctypes.windll.shcore.SetProcessDpiAwareness(1)


def _getHandle(handle: Union[int, str]) -> Optional[int]:
    newHandle = None
    if isinstance(handle, str):
        try:
            newHandle = int(handle, base=16)
        except:
            pass
    elif isinstance(handle, int):
        newHandle = handle
    return newHandle


def _getWindowBox(handle: int) -> Box:
    x, y, r, b = win32gui.GetWindowRect(handle)
    return Box(x, y, abs(r - x), abs(b - y))


def _moveResizeWindow(handle: int, newBox: Box):
    win32gui.MoveWindow(handle, newBox.left, newBox.top, newBox.width, newBox.height, True)

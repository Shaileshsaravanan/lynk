#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
assert sys.platform == "linux"

from typing import Union, Optional

from Xlib.xobject.drawable import Window as XWindow

from ._main import Box
from ewmhlib import EwmhWindow


def _getHandle(handle: Union[int, XWindow]) -> Optional[EwmhWindow]:

    newHandle = None
    if isinstance(handle, int):
        newHandle = EwmhWindow(handle)
    elif isinstance(handle, XWindow):
        newHandle = EwmhWindow(handle.id)
    return newHandle


def _getWindowBox(handle: EwmhWindow) -> Box:
    # https://stackoverflow.com/questions/12775136/get-window-position-and-size-in-python-with-xlib
    geom = handle.xWindow.get_geometry()
    pos = handle.root.translate_coords(handle.id, 0, 0)
    x = pos.x
    y = pos.y
    w = geom.width
    h = geom.height
    # Thanks to roym899 (https://github.com/roym899) for his HELP!!!!
    if "gnome" in os.environ.get('XDG_CURRENT_DESKTOP', "").lower():
        # Most apps in GNOME do not set _NET_EXTENTS, but _GTK_EXTENTS,
        # which is the additional space AROUND the window.
        _gtk_extents = handle._getGtkFrameExtents()
        if _gtk_extents and len(_gtk_extents) >= 4:
            # this means there is a GTK HeaderBar
            x += int(_gtk_extents[0])
            y += int(_gtk_extents[2])
            w -= (int(_gtk_extents[0]) + int(_gtk_extents[1]))
            h -= (int(_gtk_extents[2]) + int(_gtk_extents[3]))
    # If not in GNOME: best guess is to trust pos and geom from above
    # NOTE: if you have this case and are not getting the expected result,
    #       please open an issue: https://github.com/Kalmat/PyWinBox/issues/new
    return Box(x, y, w, h)


def _moveResizeWindow(handle: EwmhWindow, newBox: Box):
    newLeft = max(0, newBox.left)  # Xlib won't accept negative positions
    newTop = max(0, newBox.top)
    newWidth = newBox.width
    newHeight = newBox.height
    if "gnome" in os.environ.get('XDG_CURRENT_DESKTOP', "").lower():
        # Most apps in GNOME do not set _NET_EXTENTS, but _GTK_EXTENTS,
        # which is the additional space AROUND the window.
        _gtk_extents = handle._getGtkFrameExtents()
        if _gtk_extents and len(_gtk_extents) >= 4:
            # this means there is a GTK HeaderBar
            newLeft -= int(_gtk_extents[0])
            newTop -= int(_gtk_extents[2])
            newWidth += (int(_gtk_extents[0]) + int(_gtk_extents[1]))
            newHeight += (int(_gtk_extents[2]) + int(_gtk_extents[3]))
    # If not in GNOME: best guess is to trust pos and geom from above
    # NOTE: if you have this case and are not getting the expected result,
    #       please open an issue: https://github.com/Kalmat/PyWinBox/issues/new
    handle.setMoveResize(x=newLeft, y=newTop, width=newWidth, height=newHeight, userAction=True)
    # handle.configure(x=newLeft, y=newTop, width=newWidth, height=newHeight)

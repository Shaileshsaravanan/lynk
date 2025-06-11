#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Union, Tuple, NamedTuple, Optional

class Box(NamedTuple):
    """Container class to handle Box struct (left, top, width, height)"""
    left: int
    top: int
    width: int
    height: int


class Rect(NamedTuple):
    """Container class to handle Rect struct (left, top, right, bottom)"""
    left: int
    top: int
    right: int
    bottom: int


class Point(NamedTuple):
    """Container class to handle Point struct (x, y)"""
    x: int
    y: int


class Size(NamedTuple):
    """Container class to handle Size struct (right, bottom)"""
    width: int
    height: int


def pointInBox(x: int, y: int, box: Box) -> bool:
    """Returns ``True`` if the ``(x, y)`` point is within the box described
    by ``(left, top, width, height)``."""
    return box.left <= x <= box.left + box.width and box.top <= y <= box.top + box.height

class PyWinBox:

    def __init__(self, onQuery: Optional[Callable[[], Box]] = None, onSet: Optional[Callable[[Box], None]] = None, handle=None):
        """
        Class to access all area/window box properties.


        ## Rectangular areas

        You just need to instantiate the PyWinBox class, passing custom callbacks to be called when any property is
        queried (onQuery) or set (onSet).

            myPyWinBox = pywinbox.PyWinBox(onQuery=customOnQuery, onSet=customOnSet)


        ## Window areas

        To manage window areas, you need to also pass the window handle when instantiating the class, in the following formats:

        - MS-Windows: integer (window id) or str (as returned by, e.g., PyQt's winId() method)
        - Linux: integer (window id) or X-Window object
        - macOS / foreign window: in case you want to manage a window from another application, you must pass target app and window names, as a tuple of strings (appName, windowTitle)
        - macOS / own window: if you want to manage your own application window, you must pass NSWindow() object

        (Search for cross-platform modules if you need a cross-platform handle. For instance, you can get this kind of handles
        using PyWinCtl's getHandle(), getAppName() or title methods)

        In this case, you can use the default, built-in methods to manage the window when its properties are queried or set
        (passing them as None):

        - default OnQuery: Will update the window position and size values when any property is queried
        - default OnSet: Will move and/or resize the window when any property is set

            PyWinBox = pywinbox.PyWinBox(onQuery=None, onSet=None, handle=windowHandle)

        Of course, you can also define (and pass) your own custom functions if you need to perform other actions on these events.

            PyWinBox = pywinbox.PyWinBox(onQuery=customOnQuery, onSet=customOnSet, handle=windowHandle))

        In this case, if your custom functions do not properly retrieve or set the actual window position and size, the
        information contained in the PyWinBox class, and returned by all properties, will likely become obsolete.

        It can raise ValueError if no parameters or not valid window handle are passed
        """
        self._handle = _getHandle(handle) if handle is not None else None
        if self._handle is None and (onSet is None or onQuery is None):
            raise ValueError
        self._onQuery: Callable[[], Box] = onQuery or self.onQuery
        self._onSet: Callable[[Box], None] = onSet or self.onSet
        self._box: Box = Box(0, 0, 0, 0)

    def onQuery(self) -> Box:
        """
        Default method to retrieve current window position and size values when a property is queried.
        It requires to pass valid window handle when instantiating the main class (PyWinBox class)

        :return: window Box struct (x, y, width, height)
        """
        if self._handle is not None:
            self._box = _getWindowBox(self._handle)
        return self._box

    def onSet(self, newBox: Box):
        """
        Default method to actually place / resize the window when a property is changed.
        It requires to pass valid window handle when instantiating the main class (PyWinBox class)

        :param newBox: target position and or size in Box struct format (x, y, width, height)
        """
        if self._handle is not None:
            _moveResizeWindow(self._handle, newBox)

    def __repr__(self):
        """Return a string of the constructor function call to create this Box object."""
        return "%s(left=%s, top=%s, width=%s, height=%s)" % (
            self.__class__.__name__,
            self._box.left,
            self._box.top,
            self._box.width,
            self._box.height,
        )

    def __str__(self):
        """Return a string representation of this Box object."""
        return "(%s, %s, %s, %s)" % (
            self._box.left,
            self._box.top,
            self._box.width,
            self._box.height,
        )

    @property
    def left(self) -> int:
        self._box = self._onQuery()
        return self._box.left

    @left.setter
    def left(self, value: int):
        self._box = self._onQuery()
        self._box = Box(value, self._box.top, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def right(self) -> int:
        self._box = self._onQuery()
        return self._box.left + self._box.width

    @right.setter
    def right(self, value: int):
        self._box = self._onQuery()
        self._box = Box(value - self._box.width, self._box.top, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def top(self) -> int:
        self._box = self._onQuery()
        return self._box.top

    @top.setter
    def top(self, value: int):
        self._box = self._onQuery()
        self._box = Box(self._box.left, value, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def bottom(self) -> int:
        self._box = self._onQuery()
        return self._box.top + self._box.height

    @bottom.setter
    def bottom(self, value: int):
        self._box = self._onQuery()
        self._box = Box(self._box.left, value - self._box.height, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def width(self) -> int:
        self._box = self._onQuery()
        return self._box.width

    @width.setter
    def width(self, value: int):
        self._box = self._onQuery()
        self._box = Box(self._box.left, self._box.top, value, self._box.height)
        self._onSet(self._box)

    @property
    def height(self) -> int:
        self._box = self._onQuery()
        return self._box.height

    @height.setter
    def height(self, value: int):
        self._box = self._onQuery()
        self._box = Box(self._box.left, self._box.top, self._box.width, value)
        self._onSet(self._box)

    @property
    def position(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left, self._box.top)

    @position.setter
    def position(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x, val.y, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def size(self) -> Size:
        self._box = self._onQuery()
        return Size(self._box.width, self._box.height)

    @size.setter
    def size(self, value: Union[Size, Tuple[int, int]]):
        val: Size = Size(*value)
        self._box = self._onQuery()
        self._box = Box(self._box.left, self._box.top, val.width, val.height)
        self._onSet(self._box)

    @property
    def box(self) -> Box:
        self._box = self._onQuery()
        return self._box

    @box.setter
    def box(self, value: Union[Box, Tuple[int, int, int, int]]):
        val: Box = Box(*value)
        self._box = val
        self._onSet(self._box)

    @property
    def rect(self) -> Rect:
        self._box = self._onQuery()
        return Rect(self._box.left, self._box.top, self._box.left + self._box.width,
                    self._box.top + self._box.height)

    @rect.setter
    def rect(self, value: Union[Rect, Tuple[int, int, int, int]]):
        val: Rect = Rect(*value)
        self._box = Box(val.left, val.top, abs(val.right - val.left), abs(val.bottom - val.top))
        self._onSet(self._box)

    @property
    def topleft(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left, self._box.top)

    @topleft.setter
    def topleft(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x, val.y, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def bottomleft(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left, self._box.top + self._box.height)

    @bottomleft.setter
    def bottomleft(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x, val.y - self._box.height, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def topright(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left + self._box.width, self._box.top)

    @topright.setter
    def topright(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x - self._box.width, val.y, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def bottomright(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left + self._box.width, self._box.top + self._box.height)

    @bottomright.setter
    def bottomright(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x - self._box.width, val.y - self._box.height, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def midtop(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left + (self._box.width // 2), self._box.top)

    @midtop.setter
    def midtop(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x - (self._box.width // 2), val.y, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def midbottom(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left + (self._box.width // 2), self._box.top + self._box.height)

    @midbottom.setter
    def midbottom(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x - (self._box.width // 2), val.y - self._box.height, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def midleft(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left, self._box.top + (self._box.height // 2))

    @midleft.setter
    def midleft(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x, val.y - (self._box.height // 2), self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def midright(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left + self._box.width, self._box.top + (self._box.height // 2))

    @midright.setter
    def midright(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x - self._box.width, val.y - (self._box.height // 2), self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def center(self) -> Point:
        self._box = self._onQuery()
        return Point(self._box.left + (self._box.width // 2), self._box.top + (self._box.height // 2))

    @center.setter
    def center(self, value: Union[Point, Tuple[int, int]]):
        val: Point = Point(*value)
        self._box = self._onQuery()
        self._box = Box(val.x - (self._box.width // 2), val.y - (self._box.height // 2), self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def centerx(self) -> int:
        self._box = self._onQuery()
        return self._box.left + (self._box.width // 2)

    @centerx.setter
    def centerx(self, value: int):
        self._box = self._onQuery()
        self._box = Box(value - (self._box.width // 2), self._box.top, self._box.width, self._box.height)
        self._onSet(self._box)

    @property
    def centery(self) -> int:
        self._box = self._onQuery()
        return self._box.top + (self._box.height // 2)

    @centery.setter
    def centery(self, value: int):
        self._box = self._onQuery()
        self._box = Box(self._box.left, value - (self._box.height // 2), self._box.width, self._box.height)
        self._onSet(self._box)


if sys.platform == "darwin":
    from ._pywinbox_macos import (_getHandle, _getWindowBox, _moveResizeWindow)

elif sys.platform == "win32":
    from ._pywinbox_win import (_getHandle, _getWindowBox, _moveResizeWindow)

elif sys.platform == "linux":
    from ._pywinbox_linux import (_getHandle, _getWindowBox, _moveResizeWindow)

else:
    raise NotImplementedError('PyWinBox currently does not support this platform. If you think you can help, please contribute! https://github.com/Kalmat/PyWinBox')

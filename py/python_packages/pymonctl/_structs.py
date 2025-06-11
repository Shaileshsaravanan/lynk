#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from enum import IntEnum
from typing import NamedTuple, Tuple
from typing_extensions import TypedDict


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


class ScreenValue(TypedDict):
    """
    Container class to handle ScreenValue struct:

        - system_name (str): name of the monitor as known by the system
        - id (int): handle/identifier of the monitor
        - is_primary (bool): ''True'' if it is the primary monitor
        - position (Point): position of the monitor
        - size (Size): size of the monitor, in pixels
        - workarea (Rect): coordinates of the usable area of the monitor usable by apps/windows (no docks, taskbars, ...)
        - scale (Tuple[int, int]): text scale currently applied to monitor
        - dpi (Tuple[int, int]): dpi values of current resolution
        - orientation (int): rotation value of the monitor as per Orientation values (NORMAL = 0,  RIGHT = 1,  INVERTED = 2, LEFT = 3)
        - frequency (float): refresh rate of the monitor
        - colordepth (int): color depth of the monitor
    """
    system_name: str
    id: int
    is_primary: bool
    position: Point
    size: Size
    workarea: Rect
    scale: Tuple[float, float]
    dpi: Tuple[int, int]
    orientation: int
    frequency: float
    colordepth: int


class DisplayMode(NamedTuple):
    """
    Container class to handle DisplayMode struct:

        - width (int): width, in pixels
        - height (int): height, in pixels
        - frequency (float): refresh rate
    """
    width: int
    height: int
    frequency: float


class Position(IntEnum):
    PRIMARY = 0
    LEFT_TOP = 10
    LEFT_BOTTOM = 11
    LEFT_CENTERED = 12
    ABOVE_LEFT = 20
    ABOVE_RIGHT = 21
    ABOVE_CENTERED = 22
    RIGHT_TOP = 30
    RIGHT_BOTTOM = 31
    RIGHT_CENTERED = 32
    BELOW_LEFT = 40
    BELOW_RIGHT = 41
    BELOW_CENTERED = 42


class Orientation(IntEnum):
    ROTATE_0 = 0
    NORMAL = 0
    ROTATE_90 = 1
    RIGHT = 1
    ROTATE_180 = 2
    INVERTED = 2
    ROTATE_270 = 3
    LEFT = 3


if sys.platform == "win32":
    import ctypes.wintypes

    # ==================================== QueryDisplayConfig =========================================

    # ==================================== PathsInfo

    class _DUMMYSTRUCTNAME(ctypes.Structure):
        _fields_ = [
            ('cloneGroupId', ctypes.c_uint32),
            ('sourceModeInfoIdx', ctypes.c_uint32)
        ]


    class _DUMMYUNIONNAME(ctypes.Union):
        _fields_ = [
            ('modeInfoIdx', ctypes.c_uint32),
            ('dummyStructName', _DUMMYSTRUCTNAME)
        ]



    class _LUID(ctypes.Structure):
        _fields_ = [
            ('lowPart', ctypes.wintypes.DWORD),
            ('highPart', ctypes.wintypes.LONG)
        ]


    class _DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
        _fields_ = [
            ('adapterId', _LUID),
            ('id', ctypes.c_uint32),
            ('dummyUnionName', _DUMMYUNIONNAME),
            ('statusFlags', ctypes.c_uint32)
        ]


    class _DISPLAYCONFIG_RATIONAL(ctypes.Structure):
        _fields_ = [
            ('numerator', ctypes.c_uint32),
            ('denominator', ctypes.c_uint32)
        ]


    class _DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
        _fields_ = [
            ('adapterId', _LUID),
            ('id', ctypes.c_uint32),
            ('dummyUnionName', _DUMMYUNIONNAME),
            ('outputTechnology', ctypes.c_uint32),
            ('rotation', ctypes.c_uint32),
            ('scaling', ctypes.c_uint32),
            ('refreshRate', _DISPLAYCONFIG_RATIONAL),
            ('scanLineOrdering', ctypes.c_uint32),
            ('targetAvailable', ctypes.c_bool),
            ('statusFlags', ctypes.c_uint32)
        ]


    class _DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
        _fields_ = [
            ('sourceInfo', _DISPLAYCONFIG_PATH_SOURCE_INFO),
            ('targetInfo', _DISPLAYCONFIG_PATH_TARGET_INFO),
            ('flags', ctypes.c_uint32)
        ]


    # ==================================== ModesInfo

    class _DISPLAYCONFIG_2DREGION(ctypes.Structure):
        _fields_ = [
            ('cx', ctypes.c_uint32),
            ('cy', ctypes.c_uint32)
        ]


    class _ADDITIONAL_SIGNAL_INFO(ctypes.Structure):
        _fields_ = [
            ('videoStandard', ctypes.c_uint32),
            ('vSyncFreqDivider', ctypes.c_uint32),
            ('reserved', ctypes.c_uint32)
        ]


    class _DUMMYUNIONNAME_MODE_SIGNAL(ctypes.Union):
        _fields_ = [
            ('additionalSignalInfo', _ADDITIONAL_SIGNAL_INFO),
            ('videoStandard', ctypes.c_uint32)
        ]


    class _DISPLAYCONFIG_VIDEO_SIGNAL_INFO(ctypes.Structure):
        _fields_ = [
            ('pixelRate', ctypes.c_uint64),
            ('hSyncFreq', _DISPLAYCONFIG_RATIONAL),
            ('vSyncFreq', _DISPLAYCONFIG_RATIONAL),
            ('activeSize', _DISPLAYCONFIG_2DREGION),
            ('totalSize', _DISPLAYCONFIG_2DREGION),
            ('dummyUnionName', _DUMMYUNIONNAME_MODE_SIGNAL),
            ('scanLineOrdering', ctypes.c_uint32)
        ]


    class _DISPLAYCONFIG_TARGET_MODE(ctypes.Structure):
        _fields_ = [
            ('targetVideoSignalInfo', _DISPLAYCONFIG_VIDEO_SIGNAL_INFO)
        ]


    class _POINTL(ctypes.Structure):
        _fields_ = [
            ('x', ctypes.wintypes.LONG),
            ('y', ctypes.wintypes.LONG)
        ]


    class _DISPLAYCONFIG_SOURCE_MODE(ctypes.Structure):
        _fields_ = [
            ('width', ctypes.c_uint32),
            ('height', ctypes.c_uint32),
            ('pixelFormat', ctypes.c_uint32),
            ('position', _POINTL)
        ]


    class _RECTL(ctypes.Structure):
        _fields_ = [
            ('left', ctypes.c_uint32),
            ('top', ctypes.c_uint32),
            ('right', ctypes.c_uint32),
            ('bottom', ctypes.c_uint32)
        ]


    class _DISPLAYCONFIG_DESKTOP_IMAGE_INFO(ctypes.Structure):
        _fields_ = [
            ('pathSourceSize', _POINTL),
            ('desktopImageRegion', _RECTL),
            ('desktopImageClip', _RECTL)
        ]


    class _DUMMYUNIONNAME_MODE(ctypes.Union):
        _fields_ = [
            ('targetMode', _DISPLAYCONFIG_TARGET_MODE),
            ('sourceMode', _DISPLAYCONFIG_SOURCE_MODE),
            ('desktopImageInfo', _DISPLAYCONFIG_DESKTOP_IMAGE_INFO)
        ]


    class _DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
        _fields_ = [
            ('infoType', ctypes.c_uint32),
            ('id', ctypes.c_uint32),
            ('adapterId', _LUID),
            ('dummyUnionName', _DUMMYUNIONNAME_MODE)
        ]


    _QDC_ONLY_ACTIVE_PATHS = 2
    _DISPLAYCONFIG_PATH_ACTIVE = 1


    # ==================================== DisplayConfig[Get/Set]DeviceInfo =========================================


    _DPI_VALUES = [100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500]


    class _DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
        _fields_ = [
            ('type', ctypes.c_uint32),
            ('size', ctypes.c_uint32),
            ('adapterId', _LUID),
            ('id', ctypes.c_uint32)
        ]


    _DISPLAYCONFIG_DEVICE_INFO_GET_DPI_SCALE = -3  # returns min, max, and currently applied DPI scaling values


    class _DISPLAYCONFIG_SOURCE_DPI_SCALE_GET(ctypes.Structure):
        _fields_ = [
            ('header', _DISPLAYCONFIG_DEVICE_INFO_HEADER),
            ('minScaleRel', ctypes.c_uint32),
            ('curScaleRel', ctypes.c_uint32),
            ('maxScaleRel', ctypes.c_uint32)
        ]


    _DISPLAYCONFIG_DEVICE_INFO_SET_DPI_SCALE = -4  # set current dpi scaling value for a display


    class _DISPLAYCONFIG_SOURCE_DPI_SCALE_SET(ctypes.Structure):
        _fields_ = [
            ('header', _DISPLAYCONFIG_DEVICE_INFO_HEADER),
            ('scaleRel', ctypes.c_uint32)
        ]


    _DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME = 2


    class _DISPLAY_CONFIG_TARGET_DEVICE_NAME(ctypes.Structure):
        _fields_ = [
            ('header', _DISPLAYCONFIG_DEVICE_INFO_HEADER),
            ('flags', ctypes.c_uint32),
            ('outputTechnology', ctypes.c_uint32),
            ('edidManufactureId', ctypes.c_uint16),
            ('edidProductCodeId', ctypes.c_uint16),
            ('connectorInstance', ctypes.c_uint32),
            ('monitorFriendlyDeviceName', ctypes.wintypes.WCHAR * 64),
            ('monitorDevicePath', ctypes.wintypes.WCHAR * 128)
        ]


    _DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME = 1


    class _DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
        _fields_ = [
            ('header', _DISPLAYCONFIG_DEVICE_INFO_HEADER),
            ('viewGdiDeviceName', ctypes.wintypes.WCHAR * 32)
        ]

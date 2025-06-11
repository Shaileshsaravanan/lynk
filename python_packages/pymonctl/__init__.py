#!/usr/bin/python
# -*- coding: utf-8 -*-

__all__ = [
    "getAllMonitors", "getAllMonitorsDict", "getMonitorsCount", "getPrimary",
    "findMonitorsAtPoint", "findMonitorsAtPointInfo", "findMonitorWithName", "findMonitorWithNameInfo",
    "saveSetup", "restoreSetup", "arrangeMonitors", "getMousePos", "version", "Monitor",
    "enableUpdateInfo", "disableUpdateInfo", "isUpdateInfoEnabled", "isWatchdogEnabled", "updateWatchdogInterval",
    "plugListenerRegister", "plugListenerUnregister", "isPlugListenerRegistered",
    "changeListenerRegister", "changeListenerUnregister", "isChangeListenerRegistered",
    "DisplayMode", "ScreenValue", "Size", "Point", "Box", "Rect", "Position", "Orientation"
]

__version__ = "0.92"


def version(numberOnly: bool = True) -> str:
    """Returns the current version of PyMonCtl module, in the form ''x.x.xx'' as string"""
    return ("" if numberOnly else "PyMonCtl-")+__version__


from ._main import (getAllMonitors, getAllMonitorsDict, getMonitorsCount, getPrimary,
                    findMonitorsAtPoint, findMonitorsAtPointInfo, findMonitorWithName, findMonitorWithNameInfo,
                    saveSetup, restoreSetup, arrangeMonitors, getMousePos, Monitor,
                    enableUpdateInfo, disableUpdateInfo, isUpdateInfoEnabled, isWatchdogEnabled, updateWatchdogInterval,
                    plugListenerRegister, plugListenerUnregister, isPlugListenerRegistered,
                    changeListenerRegister, changeListenerUnregister, isChangeListenerRegistered,
                    DisplayMode, ScreenValue, Size, Point, Box, Rect, Position, Orientation
                    )

#!/usr/bin/python
# -*- coding: utf-8 -*-

__all__ = [
    "version", "PyWinBox", "Box", "Rect", "Point", "Size", "pointInBox"
]

__version__ = "0.7"


def version(numberOnly: bool = True) -> str:
    """Returns the current version of PyWinBox module, in the form ''x.x.xx'' as string"""
    return ("" if numberOnly else "PyWinBox-")+__version__


from ._main import Box, Rect, Point, Size, pointInBox, PyWinBox

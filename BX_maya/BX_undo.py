# BX_maya/BX_undo.py
from __future__ import annotations

from functools import wraps

import maya.cmds as cmds


def undo_chunk(name="BevelX Operation"):
    """
    Decorator that wraps a Maya operation in one undo chunk.

    Usage:

        @undo_chunk("BevelX Apply")
        def apply_selected_bevel(...):
            ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cmds.undoInfo(openChunk=True, chunkName=name)

            try:
                return func(*args, **kwargs)

            finally:
                cmds.undoInfo(closeChunk=True)

        return wrapper

    return decorator
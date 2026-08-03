# BX_settings.py
# BevelX default settings and constants.

TOOL_NAME = "BevelX"
TOOL_SHORT_NAME = "Bx"
VERSION = "0.1.0"

AFFECT_EDGES = "EDGES"
AFFECT_VERTICES = "VERTICES"

WIDTH_OFFSET = "OFFSET"
WIDTH_WIDTH = "WIDTH"
WIDTH_DEPTH = "DEPTH"
WIDTH_PERCENT = "PERCENT"
WIDTH_ABSOLUTE = "ABSOLUTE"

PROFILE_SUPERELLIPSE = "SUPERELLIPSE"
PROFILE_CUSTOM = "CUSTOM"

MITER_SHARP = "SHARP"
MITER_PATCH = "PATCH"
MITER_ARC = "ARC"

DEFAULT_SETTINGS = {
    "affect": AFFECT_EDGES,
    "width_type": WIDTH_OFFSET,
    "width": 0.1,
    "segments": 1,
    "profile_shape": 0.5,
    "profile_type": PROFILE_SUPERELLIPSE,
    "profile_preset": "Default",
    "miter_outer": MITER_SHARP,
    "miter_inner": MITER_SHARP,
    "clamp_overlap": True,
    "loop_slide": True,
    "harden_normals": False,
    "mark_sharp": False,
    "mark_seam": False,
    "material_index": -1,
    "debug_draw": True,
}


def copy_defaults():
    """Return a mutable copy of the default BevelX settings."""
    return dict(DEFAULT_SETTINGS)

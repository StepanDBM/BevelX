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

INNER_CAP_AUTO = "AUTO"
INNER_CAP_NGON = "NGON"
INNER_CAP_FAN = "FAN"
INNER_CAP_ADJ_LITE = "ADJ_LITE"

POLE_CAP_AUTO = "AUTO"
POLE_CAP_NGON = "NGON"
POLE_CAP_FAN = "FAN"
POLE_CAP_ADJ_LITE = "ADJ_LITE"

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

    "inner_cap_mode": INNER_CAP_AUTO,
    "pole_cap_mode": POLE_CAP_AUTO,

    "clamp_overlap": True,
    "loop_slide": True,
    "harden_normals": False,
    "mark_sharp": False,
    "mark_seam": False,
    "material_index": -1,
    "debug_draw": True,

    # Logging
    "log_level": "INFO",

    # Default visible channels
    "log_settings": True,
    "log_summary": True,
    "log_audit": True,
    "log_audit_clean": False,
    "log_topology": True,

    # Noisy opt-in channels
    "log_reload": False,
    "log_rails": False,
    "log_boundary": False,
    "log_miter": False,
    "log_support": False,
    "log_caps": False,
    "log_transaction": False,
    "log_transaction_dump": False,
    "log_append": False
}

def copy_defaults():
    """Return a mutable copy of the default BevelX settings."""
    return dict(DEFAULT_SETTINGS)

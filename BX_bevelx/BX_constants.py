# BX_bevelx/BX_constants.py
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Blender bevel epsilon constants.
# Ported from bmesh_bevel.cc constants.
# ---------------------------------------------------------------------------

BEVEL_EPSILON_D = 1.0e-6
BEVEL_EPSILON = 1.0e-6
BEVEL_EPSILON_SQ = 1.0e-12
BEVEL_EPSILON_BIG = 1.0e-4
BEVEL_EPSILON_BIG_SQ = 1.0e-8

BEVEL_EPSILON_ANG = math.radians(2.0)
BEVEL_SMALL_ANG = math.radians(10.0)
BEVEL_SMALL_ANG_DOT = 1.0 - math.cos(BEVEL_SMALL_ANG)
BEVEL_EPSILON_ANG_DOT = 1.0 - math.cos(BEVEL_EPSILON_ANG)

BEVEL_MAX_ADJUST_PCT = 10.0
BEVEL_MAX_AUTO_ADJUST_PCT = 300.0
BEVEL_MATCH_SPEC_WEIGHT = 0.2

BEVEL_GOOD_ANGLE = 0.0001


# ---------------------------------------------------------------------------
# Profile constants.
# Blender uses these exact conceptual profile values.
# ---------------------------------------------------------------------------

PRO_SQUARE_R = 1.0e4
PRO_CIRCLE_R = 2.0
PRO_LINE_R = 1.0
PRO_SQUARE_IN_R = 0.0


# ---------------------------------------------------------------------------
# VMesh kinds.
# These mirror Blender's VMesh::mesh_kind enum.
# ---------------------------------------------------------------------------

M_NONE = "M_NONE"
M_POLY = "M_POLY"
M_ADJ = "M_ADJ"
M_TRI_FAN = "M_TRI_FAN"
M_CUTOFF = "M_CUTOFF"


# ---------------------------------------------------------------------------
# Face kind.
# Blender has this enum internally. We keep names, but this is metadata only.
# This is not BevelX transaction architecture.
# ---------------------------------------------------------------------------

F_NONE = "F_NONE"
F_ORIG = "F_ORIG"
F_VERT = "F_VERT"
F_EDGE = "F_EDGE"
F_RECON = "F_RECON"


# ---------------------------------------------------------------------------
# Angle kind.
# ---------------------------------------------------------------------------

ANGLE_SMALLER = -1
ANGLE_STRAIGHT = 0
ANGLE_LARGER = 1


# ---------------------------------------------------------------------------
# Bevel profile and mode constants.
# These are Maya-side symbolic values for now, matching Blender concepts.
# ---------------------------------------------------------------------------

BEVEL_PROFILE_SUPERELLIPSE = "SUPERELLIPSE"
BEVEL_PROFILE_CUSTOM = "CUSTOM"

BEVEL_AFFECT_EDGES = "EDGES"
BEVEL_AFFECT_VERTICES = "VERTICES"

BEVEL_AMT_OFFSET = "OFFSET"
BEVEL_AMT_WIDTH = "WIDTH"
BEVEL_AMT_DEPTH = "DEPTH"
BEVEL_AMT_PERCENT = "PERCENT"
BEVEL_AMT_ABSOLUTE = "ABSOLUTE"

BEVEL_MITER_SHARP = "SHARP"
BEVEL_MITER_ARC = "ARC"
BEVEL_MITER_PATCH = "PATCH"

BEVEL_VMESH_ADJ = "ADJ"
BEVEL_VMESH_CUTOFF = "CUTOFF"
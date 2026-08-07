# BX_bootstrap.py

"""
Package-scanning reloaders are elegant until Maya decides to be Maya.
For now I will be using a hardcoded ordered module list.
Deterministic, boring, reliable.
Beautiful stupid little brick.
"""

from __future__ import print_function

import os
import sys
import importlib

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(PACKAGE_DIR)

from BX_profile import BX_log

MODULES_TO_RELOAD = [
    # Core
    "BX_core.BX_settings",
    "BX_profile.BX_log",
    "BX_core.BX_context",
    "BX_core.BX_session",
    # Math / solver foundation
    "BX_math.BX_math",
    "BX_math.BX_offset",
    "BX_math.BX_clamp",
    # Mesh / topology
    "BX_mesh.BX_selection",
    "BX_mesh.BX_bmesh",
    "BX_mesh.BX_mesh",
    "BX_mesh.BX_edgeHalf",
    "BX_mesh.BX_bevelVertex",
    # Profile system
    "BX_profile.BX_profile",
    # Boundary / corner systems
    #"BX_boundary.BX_boundary",
    "BX_boundary.BX_boundvert",
    "BX_boundary.BX_miter",
    #"BX_boundary.BX_vmesh",
    "BX_boundary.BX_vmesh_runtime",
    # Geometry creation / reconstruction
    "BX_build.BX_transaction",
    "BX_build.BX_build",
    "BX_build.BX_rebuild",
    # Output / production systems
    "BX_profile.BX_debug",
    "BX_profile.BX_audit",
    "BX_profile.BX_profile",
    "BX_profile.BX_normals",
    "BX_profile.BX_attributes",
    # Tests
    "BX_profile.BX_tests",
    # Backend entry point
    "BX_core.BX_core",
    # Root UI
    "BX_UI"
]
def ensure_path():
    for path in (PACKAGE_DIR, PARENT_DIR):
        if path and path not in sys.path:
            sys.path.insert(0, path)
            try:
                from BX_profile import BX_log
                BX_log.debug("Added to sys.path: {0}".format(path), channel="reload")
            except Exception:
                pass


def reload_module(module_name):
    try:
        module = importlib.import_module(module_name)
        importlib.reload(module)
        try:
            BX_log.debug("Reloaded: {0}".format(module_name), channel="reload")
        except Exception:
            pass
        return module

    except Exception as exc:
        print("[BevelX] Reload failed: {0}".format(module_name))
        print("[BevelX] Error: {0}".format(exc))
        raise


def reload_modules():
    ensure_path()
    for module_name in MODULES_TO_RELOAD:
        reload_module(module_name)

def launch(reload=True):
    ensure_path()
    if reload:
        reload_modules()

    import BX_UI
    importlib.reload(BX_UI)
    return BX_UI.show()

def bootstrap():
    reload_modules()
if __name__ == "__main__":
    launch(reload=True)
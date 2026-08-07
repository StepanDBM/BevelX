# BX_bootstrap.py
from __future__ import annotations

import os
import sys
import importlib


BEVELX_ROOT = os.path.dirname(os.path.abspath(__file__))

MODULE_RELOAD_ORDER = [
    # Bevel core
    "BX_bevelx.BX_constants",
    "BX_bevelx.BX_math_utils",
    "BX_bevelx.BX_types",
    "BX_bevelx.BX_mesh_model",
    "BX_bevelx.BX_build_bevverts",
    "BX_bevelx.BX_build_boundverts",
    "BX_bevelx.BX_build_vmesh",
    "BX_bevelx.BX_build_edge_polygons",
    "BX_bevelx.BX_rebuild_polygons",
    "BX_bevelx.BX_emit_maya_mesh",
    "BX_bevelx.BX_bevel_main",

    # Maya bridge
    "BX_maya.BX_mesh_read",
    "BX_maya.BX_mesh_write",
    "BX_maya.BX_mesh_bridge",

    # Optional Maya helpers, safe if missing
    "BX_maya.BX_selection",
    "BX_maya.BX_viewport_debug",

    # Launcher last
    "BX_launcher",
]


def ensure_path():
    """
    Ensure the BevelX root is available to Maya Python.
    """
    if BEVELX_ROOT not in sys.path:
        sys.path.insert(0, BEVELX_ROOT)

    return BEVELX_ROOT


def import_or_reload_module(module_name, do_reload=True):
    """
    Import or reload one module.
    Missing optional modules are skipped only if they are known optional helpers.
    """
    optional_modules = {
        "BX_maya.BX_selection",
        "BX_maya.BX_viewport_debug",
    }

    try:
        if module_name in sys.modules:
            module = sys.modules[module_name]
            if do_reload:
                module = importlib.reload(module)
            return module

        return importlib.import_module(module_name)

    except ImportError:
        if module_name in optional_modules:
            print("[BevelX bootstrap] Optional module not found: {}".format(module_name))
            return None

        raise


def reload_modules():
    """
    Reload BevelX modules in dependency order.

    Dependency rule:
        low level modules reload first
        higher level modules reload after them
    """
    ensure_path()

    loaded = {}

    for module_name in MODULE_RELOAD_ORDER:
        module = import_or_reload_module(module_name, do_reload=True)
        loaded[module_name] = module

    return loaded


def launch(reload=True, run=None, **kwargs):
    """
    Bootstrap BevelX.

    Args:
        reload:
            Reload all BevelX modules.

        run:
            Optional command:
                None
                "debug"
                "apply"
                "shelf"

        kwargs:
            Passed to BX_launcher command functions.
    """
    ensure_path()

    if reload:
        reload_modules()

    import BX_launcher
    if reload:
        BX_launcher = importlib.reload(BX_launcher)

    if run == "debug":
        return BX_launcher.debug_selected_bevel(**kwargs)

    if run == "apply":
        return BX_launcher.apply_selected_bevel(**kwargs)

    if run == "shelf":
        return BX_launcher.install_shelf_button(**kwargs)

    print("[BevelX] Bootstrap complete.")
    return BX_launcher
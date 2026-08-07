# BX_launcher.py
from __future__ import annotations

import sys
import importlib

import maya.cmds as cmds

from BX_maya import BX_mesh_bridge


DEFAULT_WIDTH = 0.1
DEFAULT_SEGMENTS = 1
DEFAULT_PROFILE = 0.5


def reload_runtime_modules():
    """
    Reload runtime modules without re-running bootstrap.

    Useful after manually editing code while Maya is open.
    """
    modules = [
        "BX_maya.BX_mesh_read",
        "BX_maya.BX_mesh_write",
        "BX_maya.BX_mesh_bridge",
        "BX_bevelx.BX_bevel_main",
        "BX_bevelx.BX_build_bevverts",
        "BX_bevelx.BX_build_boundverts",
        "BX_bevelx.BX_build_vmesh",
        "BX_bevelx.BX_build_edge_polygons",
        "BX_bevelx.BX_rebuild_polygons",
        "BX_bevelx.BX_emit_maya_mesh",
    ]

    for module_name in modules:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])

    print("[BevelX] Runtime modules reloaded.")


def debug_selected_bevel(width=DEFAULT_WIDTH,
                         segments=DEFAULT_SEGMENTS,
                         profile=DEFAULT_PROFILE,
                         world_space=False):
    """
    Run the current BevelX debug pipeline on the selected Maya edge.

    This prints:
        BevVerts
        BoundVerts
        VMeshes
        Edge polygons
        Rebuilt polygons
        Emitted mesh summary
    """
    print("[BevelX] Debug selected bevel")
    print("[BevelX]   width={}".format(width))
    print("[BevelX]   segments={}".format(segments))
    print("[BevelX]   profile={}".format(profile))
    print("[BevelX]   world_space={}".format(world_space))

    return BX_mesh_bridge.debug_selected_mesh_bevel_pipeline(
        world_space=world_space,
        width=width,
        segments=segments,
        profile=profile,
    )


def apply_selected_bevel(name="BX_bevel_result",
                         width=DEFAULT_WIDTH,
                         segments=DEFAULT_SEGMENTS,
                         profile=DEFAULT_PROFILE,
                         world_space=False):
    """
    Run the current BevelX pipeline and create a result mesh.

    Current behavior:
        selected Maya mesh
            -> read pydata
            -> BevelX pipeline
            -> new Maya mesh

    Later behavior:
        same selected Maya shape edited locally.
    """
    print("[BevelX] Apply selected bevel")
    print("[BevelX]   result={}".format(name))
    print("[BevelX]   width={}".format(width))
    print("[BevelX]   segments={}".format(segments))
    print("[BevelX]   profile={}".format(profile))
    print("[BevelX]   world_space={}".format(world_space))

    result = BX_mesh_bridge.bevel_selected_mesh_to_new_mesh(
        name=name,
        world_space=world_space,
        width=width,
        segments=segments,
        profile=profile,
    )

    BX_mesh_bridge.print_bevel_bridge_debug(result)

    return result


def install_shelf_button(shelf_name=None):
    """
    Install BevelX shelf buttons in Maya.

    Creates:
        BevelX Apply
        BevelX Debug
        BevelX Reload
    """
    if shelf_name is None:
        shelf_name = cmds.shelfTabLayout("ShelfLayout", query=True, selectTab=True)

    if not shelf_name:
        raise RuntimeError("Could not determine active Maya shelf.")

    root_path = _get_bevelx_root_from_module()

    apply_cmd = _make_shelf_python_command(
        root_path=root_path,
        run_mode="apply"
    )

    debug_cmd = _make_shelf_python_command(
        root_path=root_path,
        run_mode="debug"
    )

    reload_cmd = _make_shelf_python_command(
        root_path=root_path,
        run_mode=None
    )

    cmds.shelfButton(
        parent=shelf_name,
        label="BX Apply",
        annotation="BevelX Apply selected bevel",
        imageOverlayLabel="BX",
        command=apply_cmd,
        sourceType="python",
    )

    cmds.shelfButton(
        parent=shelf_name,
        label="BX Debug",
        annotation="BevelX debug selected bevel",
        imageOverlayLabel="DBG",
        command=debug_cmd,
        sourceType="python",
    )

    cmds.shelfButton(
        parent=shelf_name,
        label="BX Reload",
        annotation="Reload BevelX modules",
        imageOverlayLabel="RLD",
        command=reload_cmd,
        sourceType="python",
    )

    print("[BevelX] Shelf buttons installed on shelf: {}".format(shelf_name))


def _get_bevelx_root_from_module():
    """
    Resolve BevelX root from BX_launcher.py.
    """
    import os
    return os.path.dirname(os.path.abspath(__file__))


def _make_shelf_python_command(root_path, run_mode=None):
    """
    Build a shelf-safe Python command string.
    """
    safe_path = root_path.replace("\\", "\\\\")

    if run_mode is None:
        run_line = "BX_bootstrap.launch(reload=True)"
    else:
        run_line = "BX_bootstrap.launch(reload=True, run='{}')".format(run_mode)

    return (
        "import sys\n"
        "BEVELX_PATH = r'{path}'\n"
        "if BEVELX_PATH not in sys.path:\n"
        "    sys.path.insert(0, BEVELX_PATH)\n"
        "import BX_bootstrap\n"
        "{run_line}\n"
    ).format(
        path=safe_path,
        run_line=run_line,
    )
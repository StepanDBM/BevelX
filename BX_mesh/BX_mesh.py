# BX_mesh.py
# BevelX high-level mesh adapter.

from __future__ import print_function

from BX_mesh import BX_selection
from BX_mesh import BX_bmesh
from BX_mesh import BX_bevelVertex


def get_selected_edge_data():
    """
    Legacy selected edge data path.

    Still used by current rail preview.
    """

    return BX_selection.get_selected_edges_data()


def debug_selected_edges():
    """
    Legacy selected edge debug.
    """

    return BX_selection.print_selected_edges_debug()


def get_selected_bmesh():
    """
    Build a BX_BMesh from current Maya selection.
    """

    return BX_bmesh.BX_BMesh.from_selection()


def debug_selected_bmesh():
    """
    Print topology summary for current selection.
    """

    bm = get_selected_bmesh()

    bm.debug_print_summary()
    bm.debug_print_selected_edges()

    return bm


def build_bevel_vertices_from_bmesh(bm):
    """
    Build BevelVertex objects from an existing BX_BMesh.
    """

    return BX_bevelVertex.build_bevel_vertices_from_bmesh(bm)


def debug_bevel_vertices_from_bmesh(bm):
    """
    Build and print BevelVertex objects from an existing BX_BMesh.
    """

    bevel_vertices = build_bevel_vertices_from_bmesh(bm)

    BX_bevelVertex.debug_print_bevel_vertices(bevel_vertices)

    return bevel_vertices
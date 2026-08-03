# BX_core.py
# Public backend API for BevelX.
from __future__ import print_function

import maya.cmds as cmds

from BX_core import BX_settings
from BX_core import BX_session
from BX_mesh import BX_mesh
from BX_build import BX_build
from BX_build import BX_transaction
from BX_build import BX_rebuild
from BX_math import BX_offset
from BX_profile import BX_debug
from BX_boundary import BX_boundary



def log(message):
    print("[BevelX] {0}".format(message))

def restore_selection(selection):
    """
    Restore Maya selection after debug drawing.

    Args:
        selection:
            List from cmds.ls(selection=True, flatten=True).
    """

    try:
        if selection:
            cmds.select(selection, replace=True)
        else:
            cmds.select(clear=True)
    except Exception as exc:
        log("Could not restore selection: {0}".format(exc))

def preview(settings=None):
    """
    Preview BevelX result.

    Current behavior:
        - capture current selection
        - build BX_BMesh
        - build BevelVertices
        - build boundaries
        - build transaction / selection transaction
        - draw debug preview
        - restore original selection
    """

    if settings is None:
        settings = BX_settings.copy_defaults()

    original_selection = cmds.ls(selection=True, flatten=True) or []

    try:
        log("Preview requested.")
        log_settings(settings)

        session = BX_session.start_or_rebuild_session(
            settings=settings,
            rail_builder=build_preview_offset_rails
        )

        session.debug_print()

        if session.last_error:
            log(session.last_error)

            if session.last_error:
                log(session.last_error)
                if not session.edges_data:
                    return settings
                log("Preview is continuing in diagnostic mode.")

        if session.bm:
            session.bm.debug_print_summary()
            session.bm.debug_print_selected_edges()

        if session.bevel_vertices:
            from BX_mesh import BX_bevelVertex

            BX_bevelVertex.debug_print_bevel_vertices(session.bevel_vertices)
            if session.bm:
                BX_boundary.debug_print_bevel_vertex_topology_classification(
                    session.bm,
                    session.bevel_vertices
                )
            else:
                BX_boundary.debug_print_bevel_vertex_classification(session.bevel_vertices)

        printed_boundaries = False

        for edge_data in session.edges_data:
            edge_id = edge_data["edge_id"]

            log_edge_data(edge_data)

            rails = session.rails_by_edge_id.get(edge_id, [])
            vertex_boundaries = session.boundaries_by_edge_id.get(edge_id, {})

            for rail_data in rails:
                rail = rail_data["rail"]

                log("  Rail for face {0}: {1} -> {2}".format(
                    rail_data["face_id"],
                    rail[0],
                    rail[1]
                ))

                if "side" in rail_data:
                    log("    Chosen side: {0}, score: {1}".format(
                        rail_data["side"],
                        rail_data.get("score")
                    ))

                if "center" in rail_data:
                    log("    Face center: {0}".format(
                        rail_data["center"]
                    ))

            if not printed_boundaries:
                BX_boundary.debug_print_boundaries(vertex_boundaries)
                printed_boundaries = True

        if session.selection_transaction is not None:
            session.selection_transaction.debug_print()

        draw_session_preview(session, settings)

        return settings

    finally:
        restore_selection(original_selection)

def apply(settings=None):
    """
    Apply BevelX result.

    Current milestone:
        - one selected manifold edge
        - transaction-driven local edit
        - uses current session if available
        - otherwise builds a session first
    """

    if settings is None:
        settings = BX_settings.copy_defaults()

    log("Apply requested.")
    log_settings(settings)

    session = BX_session.get_current_session()

    if not session.active or not session.has_transaction():
        session = BX_session.start_or_rebuild_session(
            settings=settings,
            rail_builder=build_preview_offset_rails
        )

    session.debug_print()

    if session.last_error:
        log("Apply blocked: {0}".format(session.last_error))
        return settings

    transaction = session.get_single_transaction()

    if transaction is None:
        log("Apply failed: session has no transaction.")
        return settings

    if not transaction.faces:
        log("Apply failed: transaction has no faces.")
        return settings

    transaction.debug_print()

    result = BX_build.apply_transaction_local_edit(
        bm=session.bm,
        transaction=transaction,
        settings=settings
    )

    if result:
        log("Apply transaction-modified mesh: {0}".format(result))
        BX_session.clear_session()
    else:
        log("Apply failed.")

    return settings

def reset():
    """
    Reset backend state.

    Clears:
        - active BevelX session
        - debug/preview objects
    """

    log("Reset requested.")

    BX_session.clear_session()
    BX_debug.clear_debug()

    return BX_settings.copy_defaults()


def build_preview_offset_rails(edge_data, settings):
    """
    Generate debug offset rails for a selected edge.

    For now:
        - Offset mode only.
        - One rail per connected face.
        - No corner solving yet.
    """

    p0, p1 = edge_data["vertex_positions"]
    width = settings.get("width", 0.1)

    rails = []

    for face_data in edge_data["faces"]:
        normal = face_data["normal"]

        # First simple convention:
        # Use left=True for all face rails.
        # Once I inspect real viewport behavior, I may flip per-face based on winding.
        face_center = face_data["center"]

        rail_result = BX_offset.offset_rail_on_face_towards_point(
            p0,
            p1,
            normal,
            width,
            target_point=face_center
        )

        rail = rail_result["rail"]

        rails.append({
            "face_id": face_data["face_id"],
            "normal": normal,
            "center": face_center,
            "side": rail_result["side"],
            "score": rail_result["score"],
            "rail": rail,
        })

        log("  Rail for face {0}: {1} -> {2}".format(
            face_data["face_id"],
            rail[0],
            rail[1]
        ))

        log("    Chosen side: {0}, score: {1}".format(
            rail_result["side"],
            rail_result["score"]
        ))

        log("    Face center: {0}".format(face_center))

    return rails

#================================================================
# Update preview methods
#================================================================

def draw_session_preview(session, settings):
    """
    Draw the current BevelX session preview.

    Draws:
        - selected edge debug
        - offset rails
        - boundary vertices
        - selection transaction faces once
    """

    if not settings.get("debug_draw", True):
        return

    BX_debug.clear_debug()

    drawn_boundaries = False

    for edge_data in session.edges_data:
        edge_id = edge_data["edge_id"]

        rails = session.rails_by_edge_id.get(edge_id, [])
        vertex_boundaries = session.boundaries_by_edge_id.get(edge_id, {})

        BX_debug.draw_edge_debug(edge_data)
        BX_debug.draw_offset_rails(edge_data, rails)

        # For multi-edge, every edge can point to the same full selection
        # boundary dictionary, so draw boundaries once.
        if not drawn_boundaries:
            BX_debug.draw_boundary_vertices(vertex_boundaries)
            drawn_boundaries = True

    if session.selection_transaction is not None:
        BX_debug.draw_transaction_faces(session.selection_transaction)

def update_preview(settings=None):
    """
    Rebuild the active BevelX preview.

    Future UI slider/value-change hook.
    """

    if settings is None:
        settings = BX_settings.copy_defaults()

    original_selection = cmds.ls(selection=True, flatten=True) or []

    try:
        log("Update preview requested.")
        log_settings(settings)

        session = BX_session.rebuild_session(
            settings=settings,
            rail_builder=build_preview_offset_rails
        )

        session.debug_print()

        if session.last_error:
            log(session.last_error)
            return settings

        draw_session_preview(session, settings)

        return settings

    finally:
        restore_selection(original_selection)

def log_settings(settings):
    for key in sorted(settings.keys()):
        log("  {0}: {1}".format(key, settings[key]))


def log_edge_data(edge_data):
    log("Edge: {0}".format(edge_data["component"]))
    log("  Mesh node: {0}".format(edge_data["node"]))
    log("  Shape: {0}".format(edge_data["shape"]))
    log("  Edge ID: {0}".format(edge_data["edge_id"]))
    log("  Vertex IDs: {0}".format(edge_data["vertex_ids"]))
    log("  Vertex positions:")
    log("    A: {0}".format(edge_data["vertex_positions"][0]))
    log("    B: {0}".format(edge_data["vertex_positions"][1]))
    log("  Connected faces: {0}".format(len(edge_data["faces"])))

    for face_data in edge_data["faces"]:
        log("    Face: {0}".format(face_data["component"]))
        log("      Face ID: {0}".format(face_data["face_id"]))
        log("      Normal: {0}".format(face_data["normal"]))

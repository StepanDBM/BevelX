# BX_session.py
# BevelX bevel session state.
#
# This module owns the current interactive bevel session.
#
# Important idea:
#   The source mesh / selection is captured once.
#   Parameter changes rebuild the transaction from that captured source.
#   Apply commits the latest transaction once.
#
# This prevents:
#   width 0.1 -> bevel mesh
#   width 0.2 -> bevel already-beveled mesh
#   width 0.3 -> bevel twice-beveled mesh
#
# Instead:
#   original source + current settings -> transaction

from __future__ import print_function

import maya.cmds as cmds

from BX_core import BX_settings
from BX_mesh import BX_mesh
from BX_boundary import BX_boundary
from BX_build import BX_transaction


class BX_BevelSession(object):
    """
    Current BevelX interactive session.

    Holds:
        - source selection
        - source BMesh
        - settings
        - bevel vertices
        - boundary vertices
        - transaction

    This object does not directly edit Maya geometry.
    """

    def __init__(self):
        self.active = False

        self.source_selection = []
        self.source_node = None

        self.settings = None

        self.bm = None
        self.edges_data = []

        self.bevel_vertices = None
        self.rails_by_edge_id = {}
        self.boundaries_by_edge_id = {}
        self.transactions_by_edge_id = {}
        self.selection_transaction = None

        self.last_error = None

    def clear(self):
        self.active = False

        self.source_selection = []
        self.source_node = None

        self.settings = None

        self.bm = None
        self.edges_data = []

        self.bevel_vertices = None
        self.rails_by_edge_id = {}
        self.boundaries_by_edge_id = {}
        self.transactions_by_edge_id = {}
        self.selection_transaction = None

        self.last_error = None

    def has_transaction(self):
        """
        Return True if this session has a transaction.
        """

        if self.selection_transaction is not None:
            return True

        return bool(self.transactions_by_edge_id)

    def get_single_transaction(self):
        """
        Return the current transaction.

        Current Apply path still only commits supported single-edge transactions.
        """

        if self.selection_transaction is not None:
            return self.selection_transaction

        if not self.transactions_by_edge_id:
            return None

        keys = sorted(self.transactions_by_edge_id.keys())

        return self.transactions_by_edge_id[keys[0]]

    def debug_print(self):
        print("[BevelX] Session:")
        print("[BevelX]   active: {0}".format(self.active))
        print("[BevelX]   source node: {0}".format(self.source_node))
        print("[BevelX]   source selection: {0}".format(self.source_selection))
        print("[BevelX]   edge count: {0}".format(len(self.edges_data)))
        print("[BevelX]   transactions: {0}".format(sorted(self.transactions_by_edge_id.keys())))
        print("[BevelX]   selection transaction: {0}".format(
            self.selection_transaction is not None
        ))

        if self.last_error:
            print("[BevelX]   last error: {0}".format(self.last_error))


CURRENT_SESSION = BX_BevelSession()


# -----------------------------------------------------------------------------
# Session lifecycle
# -----------------------------------------------------------------------------

def get_current_session():
    return CURRENT_SESSION


def clear_session():
    """
    Clear current BevelX session state.

    Does not delete debug objects.
    BX_debug.clear_debug() should be called by the caller if needed.
    """

    CURRENT_SESSION.clear()


def start_or_rebuild_session(settings=None, rail_builder=None):
    """
    Start or rebuild the current bevel session.

    Args:
        settings:
            BevelX settings dictionary.

        rail_builder:
            Function used to build rails for one edge_data.
            Expected signature:
                rail_builder(edge_data, settings) -> rails

            This is passed in from BX_core to avoid circular imports.

    Returns:
        BX_BevelSession
    """

    if settings is None:
        settings = BX_settings.copy_defaults()

    if rail_builder is None:
        raise RuntimeError("BX_session requires a rail_builder function.")

    session = CURRENT_SESSION
    session.clear()

    session.settings = dict(settings)
    session.source_selection = cmds.ls(selection=True, flatten=True) or []

    if not session.source_selection:
        session.last_error = "Nothing selected."
        return session

    try:
        session.bm = BX_mesh.get_selected_bmesh()
        session.source_node = session.bm.node

        session.edges_data = BX_mesh.get_selected_edge_data()

        if not session.edges_data:
            session.last_error = "No selected polygon edges."
            return session

        session.bevel_vertices = BX_mesh.build_bevel_vertices_from_bmesh(session.bm)
        unsupported_reason = BX_boundary.get_unsupported_boundary_reason(session.bevel_vertices)
        requires_selection_transaction = BX_boundary.requires_selection_transaction(session.bevel_vertices)

        # Always build rails.
        for edge_data in session.edges_data:
            edge_id = edge_data["edge_id"]

            rails = rail_builder(
                edge_data,
                session.settings
            )

            session.rails_by_edge_id[edge_id] = rails

        # Build boundary diagnostics / shared boundaries for the whole selection.
        selection_boundaries = BX_boundary.build_boundaries_for_selection(
            bm=session.bm,
            edges_data=session.edges_data,
            rails_by_edge_id=session.rails_by_edge_id,
            bevel_vertices=session.bevel_vertices
        )

        # Store a per-edge view for drawing/debug convenience.
        for edge_data in session.edges_data:
            edge_id = edge_data["edge_id"]
            session.boundaries_by_edge_id[edge_id] = selection_boundaries

        # If the selection is unsupported, still build a preview transaction if possible,
        # but mark the session as errored.
        if unsupported_reason:
            # Unsupported topology, for example CORNER_3_PLUS.
            #
            # I still keep:
            #   - BMesh diagnostics
            #   - edge rails
            #   - terminal boundary diagnostics
            #
            # But I do NOT build a transaction because missing VMesh/corner
            # boundaries will create broken F_EDGE/F_RECON data.
            session.selection_transaction = None
            session.transactions_by_edge_id = {}

            session.last_error = unsupported_reason
            session.active = True

            return session

        # Multi-edge / CORNER_2 path.
        # This is now supported for Preview and Apply.
        if requires_selection_transaction or len(session.edges_data) > 1:
            session.selection_transaction = BX_transaction.build_selection_transaction(
                edges_data=session.edges_data,
                vertex_boundaries=selection_boundaries,
                bm=session.bm,
                bevel_vertices=session.bevel_vertices
            )

            if not session.selection_transaction.faces:
                session.last_error = "Could not build selection transaction: missing boundary data."
                session.active = True
                return session

            session.last_error = None
            session.active = True
            return session

        # Single-edge terminal path.
        for edge_data in session.edges_data:
            edge_id = edge_data["edge_id"]

            transaction = BX_transaction.build_single_edge_transaction(
                edge_data=edge_data,
                vertex_boundaries=selection_boundaries,
                bm=session.bm
            )

            session.transactions_by_edge_id[edge_id] = transaction
            session.selection_transaction = transaction

        session.active = True
        session.last_error = None

        for edge_data in session.edges_data:
            edge_id = edge_data["edge_id"]

            vertex_boundaries = selection_boundaries

            transaction = BX_transaction.build_single_edge_transaction(
                edge_data=edge_data,
                vertex_boundaries=vertex_boundaries,
                bm=session.bm
            )

            session.boundaries_by_edge_id[edge_id] = vertex_boundaries
            session.transactions_by_edge_id[edge_id] = transaction
            session.selection_transaction = transaction

        session.active = True
        session.last_error = None

        session.active = True
        session.last_error = None

    except Exception as exc:
        session.last_error = str(exc)
        session.active = False

    return session


def rebuild_session(settings=None, rail_builder=None):
    """
    Rebuild current session from the original source selection.

    This is the future hook for live UI slider updates.

    For now, it restores the captured source selection, then rebuilds.
    """

    session = CURRENT_SESSION

    if not session.source_selection:
        return start_or_rebuild_session(
            settings=settings,
            rail_builder=rail_builder
        )

    try:
        cmds.select(session.source_selection, replace=True)
    except Exception:
        pass

    if settings is None:
        settings = session.settings

    return start_or_rebuild_session(
        settings=settings,
        rail_builder=rail_builder
    )
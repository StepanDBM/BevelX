# BX_audit.py
# BevelX transaction audit helpers.
#
# This module does not build geometry.
# It inspects a completed BX_BevelTransaction and reports suspicious topology.

from __future__ import print_function

from BX_math import BX_math as bxm


FACE_EDGE = "F_EDGE"
FACE_VERT = "F_VERT"
FACE_RECON = "F_RECON"

VERT_ORIGINAL = "ORIGINAL"
VERT_BOUNDARY = "BOUNDARY"
VERT_GENERATED = "GENERATED"


def audit_selection_transaction(transaction,
                                bm=None,
                                edges_data=None,
                                vertex_boundaries=None,
                                bevel_vertices=None,
                                affected_vertex_ids=None,
                                affected_face_ids=None,
                                label="selection"):
    """
    Audit a completed BevelX transaction.

    Answers:
        - Did every selected edge produce one F_EDGE?
        - Did every affected face get rebuilt or intentionally replaced?
        - Did any F_RECON still contain an affected original vertex?
        - Did any boundary vertex remain unused?
        - Did any transaction face contain duplicate vertex IDs?
        - Did any transaction face have near-zero area?

    This is diagnostic only. It does not mutate the transaction.
    """

    report = {
        "label": label,
        "errors": [],
        "warnings": [],
        "info": [],
    }

    if transaction is None:
        report["errors"].append("transaction is None")
        print_audit_report(report)
        return report

    if edges_data is None:
        edges_data = []

    if vertex_boundaries is None:
        vertex_boundaries = {}

    if affected_vertex_ids is None:
        affected_vertex_ids = []

    if affected_face_ids is None:
        affected_face_ids = getattr(transaction, "faces_to_replace", [])

    audit_selected_edges_have_f_edge(
        transaction=transaction,
        edges_data=edges_data,
        report=report
    )

    audit_affected_faces_rebuilt(
        transaction=transaction,
        affected_face_ids=affected_face_ids,
        report=report
    )

    audit_recon_faces_do_not_keep_affected_original_vertices(
        transaction=transaction,
        affected_vertex_ids=affected_vertex_ids,
        report=report
    )

    audit_unused_boundary_vertices(
        transaction=transaction,
        vertex_boundaries=vertex_boundaries,
        report=report
    )

    audit_duplicate_face_vertices(
        transaction=transaction,
        report=report
    )

    audit_degenerate_transaction_faces(
        transaction=transaction,
        report=report
    )

    print_audit_report(report)

    return report


def audit_selected_edges_have_f_edge(transaction, edges_data, report):
    """
    Check that every selected edge has exactly one F_EDGE face.
    """

    selected_edge_ids = [
        edge_data.get("edge_id")
        for edge_data in edges_data
    ]

    edge_face_counts = {}

    for edge_id in selected_edge_ids:
        edge_face_counts[edge_id] = 0

    for face in transaction.faces:
        if face.face_kind != FACE_EDGE:
            continue

        source_edge_id = getattr(face, "source_edge_id", None)

        if source_edge_id in edge_face_counts:
            edge_face_counts[source_edge_id] += 1

    for edge_id in selected_edge_ids:
        count = edge_face_counts.get(edge_id, 0)

        if count == 0:
            report["errors"].append(
                "selected edge {0} did not produce an F_EDGE face".format(
                    edge_id
                )
            )

        elif count > 1:
            report["warnings"].append(
                "selected edge {0} produced {1} F_EDGE faces".format(
                    edge_id,
                    count
                )
            )


def audit_affected_faces_rebuilt(transaction, affected_face_ids, report):
    """
    Check that every affected original face has at least one transaction face
    carrying source_face_id == affected face id.

    This does not require the face to be F_RECON. An affected face may be
    represented by F_RECON, F_CAP, F_PATCH, or other patch/cap faces.
    """

    expected = set(affected_face_ids)
    found = set()

    for face in transaction.faces:
        source_face_id = getattr(face, "source_face_id", None)

        if source_face_id in expected:
            found.add(source_face_id)

    missing = sorted(expected.difference(found))

    for face_id in missing:
        report["warnings"].append(
            "affected source face {0} has no transaction face using source_face_id={0}".format(
                face_id
            )
        )


def audit_recon_faces_do_not_keep_affected_original_vertices(transaction,
                                                             affected_vertex_ids,
                                                             report):
    """
    Check whether an F_RECON face still contains an affected original vertex.

    This is often suspicious:
        support replacement failed
        fallback was not used
        old original vertex can create holes or overlaps
    """

    affected = set(affected_vertex_ids)

    if not affected:
        return

    for face in transaction.faces:
        if face.face_kind != FACE_RECON:
            continue

        for tx_id in face.vertex_ids:
            if tx_id < 0 or tx_id >= len(transaction.vertices):
                continue

            tx_vertex = transaction.vertices[tx_id]

            if tx_vertex.source != VERT_ORIGINAL:
                continue

            original_vertex_id = getattr(tx_vertex, "original_vertex_id", None)

            if original_vertex_id in affected:
                report["warnings"].append(
                    "F_RECON face {0} source_face={1} still contains affected original vertex {2} as tx vertex {3}".format(
                        face.id,
                        face.source_face_id,
                        original_vertex_id,
                        tx_id
                    )
                )


def audit_unused_boundary_vertices(transaction, vertex_boundaries, report):
    """
    Check if a boundary vertex exists in vertex_boundaries but was never used
    by any transaction face.
    """

    expected_boundary_ids = set()

    for vertex_id in vertex_boundaries.keys():
        for boundary_vertex in vertex_boundaries.get(vertex_id, []):
            boundary_id = getattr(boundary_vertex, "id", None)

            if boundary_id is not None:
                expected_boundary_ids.add(boundary_id)

    used_boundary_ids = set()

    for face in transaction.faces:
        for tx_id in face.vertex_ids:
            if tx_id < 0 or tx_id >= len(transaction.vertices):
                continue

            tx_vertex = transaction.vertices[tx_id]

            if tx_vertex.source != VERT_BOUNDARY:
                continue

            boundary_id = getattr(tx_vertex, "boundary_id", None)

            if boundary_id is not None:
                used_boundary_ids.add(boundary_id)

    unused = sorted(expected_boundary_ids.difference(used_boundary_ids))

    for boundary_id in unused:
        report["warnings"].append(
            "boundary vertex {0} was built but not used by any transaction face".format(
                boundary_id
            )
        )


def audit_duplicate_face_vertices(transaction, report):
    """
    Check whether any transaction face repeats the same tx vertex id.
    """

    for face in transaction.faces:
        vertex_ids = list(face.vertex_ids)

        if len(vertex_ids) != len(set(vertex_ids)):
            report["errors"].append(
                "transaction face {0} kind={1} has duplicate vertex ids: {2}".format(
                    face.id,
                    face.face_kind,
                    vertex_ids
                )
            )


def audit_degenerate_transaction_faces(transaction, report, area_epsilon=1.0e-8):
    """
    Check whether transaction faces are near-zero area.
    """

    for face in transaction.faces:
        vertex_ids = list(face.vertex_ids)

        if len(vertex_ids) < 3:
            report["errors"].append(
                "transaction face {0} kind={1} has fewer than 3 vertices: {2}".format(
                    face.id,
                    face.face_kind,
                    vertex_ids
                )
            )
            continue

        area = transaction_polygon_area(
            transaction=transaction,
            vertex_ids=vertex_ids
        )

        if area <= area_epsilon:
            report["warnings"].append(
                "transaction face {0} kind={1} appears degenerate: area={2}, verts={3}".format(
                    face.id,
                    face.face_kind,
                    area,
                    vertex_ids
                )
            )


def transaction_polygon_area(transaction, vertex_ids):
    """
    Approximate polygon area by triangulating from the first vertex.
    """

    if len(vertex_ids) < 3:
        return 0.0

    first = transaction.vertices[vertex_ids[0]].co_world
    area = 0.0

    for i in range(1, len(vertex_ids) - 1):
        a = first
        b = transaction.vertices[vertex_ids[i]].co_world
        c = transaction.vertices[vertex_ids[i + 1]].co_world

        area += triangle_area_from_points(a, b, c)

    return area


def triangle_area_from_points(a, b, c):
    """
    Return triangle area from three world-space points.
    """

    ab = bxm.sub(b, a)
    ac = bxm.sub(c, a)

    cross_value = bxm.cross(ab, ac)

    return 0.5 * bxm.length(cross_value)


def print_audit_report(report):
    from BX_profile import BX_log

    label = report.get("label", "selection")
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])
    info = report.get("info", [])

    has_signal = bool(errors or warnings or info)

    if not has_signal:
        BX_log.audit_clean(
            "[AUDIT] {0}: errors=0, warnings=0, info=0".format(label)
        )
        return

    BX_log.audit(
        "[AUDIT] {0}: errors={1}, warnings={2}, info={3}".format(
            label,
            len(errors),
            len(warnings),
            len(info)
        )
    )

    for message in errors:
        BX_log.error("[AUDIT] {0}".format(message), channel="audit")

    for message in warnings:
        BX_log.warn("[AUDIT] {0}".format(message), channel="audit")

    for message in info:
        BX_log.info("[AUDIT] {0}".format(message), channel="audit")
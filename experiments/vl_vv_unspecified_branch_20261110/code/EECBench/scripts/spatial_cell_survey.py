"""Fixed spatial attention for a candidate-blind diagnostic; no new output gate.

Reuse the admitted blind survey schema, fourteen views and geometry validator.
Cell coordinates guide inspection only; they do not establish physical scope.
"""
from __future__ import annotations

from collections.abc import Mapping
import json

from blind_pixel_survey import build_survey_prompt

POLICY_VERSION = "spatial_cell_survey_v0.1"
CELL_ORDER = ("TL", "TR", "BL", "BR")
INSTRUCTIONS = """Fixed spatial inspection responsibility:
Inspect your assigned cell at each of the six original-frame time points. The
cell table below uses ORIGINAL full-frame pixel coordinates, half-open xyxy:
mx=floor(width/2), my=floor(height/2); TL=[0,0,mx,my], TR=[mx,0,width,my],
BL=[0,my,mx,height], BR=[mx,my,width,height]. Midline pixels belong to the
right/bottom cells. Cell borders are attention boundaries, not new image crops
or physical boundaries. Existing overlapping crop views do not change them.

Use all supplied views to understand the full visible scope, occlusion and
possible continuity of observations encountered in your assigned cell. Do not
turn unrelated areas into a new global inventory. A track's conceptual home
frame is the earliest supplied original frame in which some visible part of
that scope can be directly localized inside your assigned cell. It need not be
the first frame or the scope's first appearance in the full image. Different
roles may have different home frames for the same scope, without proving its
identity. If localization is unreliable, preserve uncertainty; do not
invent a box or borrow one from a later frame to establish a home frame. This
is an inspection and later-audit concept, not a required new output field.

A visible region may cross a cell border and appear in more than one role's
observations. Do not split a physical scope mechanically at the cell border.
Retain visible boundaries outside your assigned cell when supported within the
selected view. Each region still belongs to its actual frame_id and view_id,
and its bbox_xyxy remains in that VIEW'S LOCAL pixels, not the cell table's
original-frame coordinates. Never complete unseen extent beyond a crop edge
or behind an occluder. Keep the original whole/part/collection/unknown,
clear/partial/uncertain and null-box rules without any new output fields.
Determine responsibility in the original full frame first, then use the chosen
view to inspect it; never treat original cell bounds as crop-local coordinates.
The view_cell_intersections table supplies each cell's intersection with each
view in VIEW-LOCAL half-open pixels. Use the entry for your assigned cell. A
null intersection means that view contains no pixels of that cell, not that
the view has no observations or that any scope is absent or out_of_view.

Every provisional track still has states for all six original frames. Leaving
your assigned cell while remaining inside the original full frame is NOT
out_of_view. Other views may support the same scope's visible portion after
it leaves the cell or before its home frame. Do not invent identity or copy a
different frame's geometry.
Use uncertain when correspondence is unresolved. Keep relations sparse under
the original survey policy. There is no observation quota or target count.
Empty, partial, uncertain, cross-cell and repeated observations remain valid
under the existing schema and geometry rules. Cell intersection, shared labels
or shared track IDs do not prove identity, accuracy or complete discovery.
"""


def build_spatial_survey_prompt(view_bundle: Mapping, assigned_cell: str) -> str:
    """Append one fixed policy and safe geometry to the byte-identical base.

    The existing builder validates the fourteen-view metadata without image I/O.
    Extra input text, paths and source/candidate metadata are never interpolated.
    All four roles differ only in the assigned_cell value of the parameter block.
    """
    if type(assigned_cell) is not str or assigned_cell not in CELL_ORDER:
        raise ValueError("assigned_cell must be TL, TR, BL or BR")
    base = build_survey_prompt(view_bundle)
    frames = []
    for view in view_bundle["views"][:6]:
        width, height = view["source_size"]
        mx, my = width // 2, height // 2
        frames.append({
            "frame_id": view["frame_id"],
            "original_view_id": view["view_id"],
            "original_size": [width, height],
            "cells_xyxy": {
                "TL": [0, 0, mx, my], "TR": [mx, 0, width, my],
                "BL": [0, my, mx, height], "BR": [mx, my, width, height],
            },
        })
    by_frame = {row["frame_id"]: row["cells_xyxy"] for row in frames}
    intersections = []
    for view in view_bundle["views"]:
        vx0, vy0, vx1, vy1 = view["crop_xyxy"]
        local = {}
        for cell, (cx0, cy0, cx1, cy1) in by_frame[view["frame_id"]].items():
            x0, y0 = max(vx0, cx0), max(vy0, cy0)
            x1, y1 = min(vx1, cx1), min(vy1, cy1)
            local[cell] = ([x0-vx0, y0-vy0, x1-vx0, y1-vy0]
                           if x0 < x1 and y0 < y1 else None)
        intersections.append({"view_id": view["view_id"], "frame_id": view["frame_id"],
                              "cells_xyxy_view_local": local})
    parameters = {"assigned_cell": assigned_cell, "original_frame_cells": frames,
                  "view_cell_intersections": intersections}
    return (base + "\n\n" + INSTRUCTIONS + "\nSpatial inspection policy: "
            + POLICY_VERSION + "\nSpatial parameters (original pixels):\n"
            + json.dumps(parameters, sort_keys=True, indent=2))

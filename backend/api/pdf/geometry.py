"""Grid geometry for the printed log, and the coordinate flip reportlab needs.

The on-screen sheet is drawn in SVG, whose origin is TOP-left with y increasing
downward. ReportLab's origin is BOTTOM-left with y increasing upward. Getting
that backwards flips the whole log vertically -- Off Duty ends up where On Duty
should be -- so the conversion happens in exactly one function here, `to_pdf_y`,
and every drawing call goes through it.

The minutes-to-x math is the same formula the SVG renderer uses. It cannot
literally share that code (that renderer is JavaScript in the frontend), so
instead it is defined once here and pinned by a parity test asserting the same
anchor positions the JavaScript test asserts: minute 0 at the left edge, 1440 at
the right, 720 exactly half way, 360 at a quarter.
"""

MINUTES_PER_DAY = 1440

# Row order, top to bottom, exactly as printed on the form.
ROWS = [
    ("off_duty", "1. Off Duty"),
    ("sleeper", "2. Sleeper Berth"),
    ("driving", "3. Driving"),
    ("on_duty", "4. On Duty (Not Driving)"),
]
ROW_INDEX = {status: index for index, (status, _label) in enumerate(ROWS)}


def minute_to_x(minute: float, grid_x: float, grid_w: float) -> float:
    """Minutes from midnight -> x. Clamped, so bad data cannot draw off the page.

    Same formula as the SVG renderer's `minuteToX`.
    """
    try:
        value = float(minute)
    except (TypeError, ValueError):
        value = 0.0
    clamped = max(0.0, min(float(MINUTES_PER_DAY), value))
    return grid_x + (clamped / MINUTES_PER_DAY) * grid_w


def row_top_from_top(index: int, grid_top: float, row_h: float) -> float:
    """Top edge of a row, measured DOWN from the top of the page."""
    return grid_top + index * row_h


def row_center_from_top(status: str, grid_top: float, row_h: float) -> float | None:
    """Centre line of a row -- where the trace is drawn -- measured from the top."""
    index = ROW_INDEX.get(status)
    if index is None:
        return None
    return grid_top + index * row_h + row_h / 2


def to_pdf_y(y_from_top: float, page_height: float) -> float:
    """Convert a top-left y into reportlab's bottom-left y.

    The single place the flip happens. Everything else in this package thinks in
    familiar screen coordinates and converts at the moment of drawing.
    """
    return page_height - y_from_top


def is_drawable(segment) -> bool:
    """A segment can be drawn only if its status is known and it has real width."""
    status = getattr(segment, "status", None)
    start = getattr(segment, "start_minute", None)
    end = getattr(segment, "end_minute", None)
    if status not in ROW_INDEX:
        return False
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return False
    return end > start


def ordered_segments(segments):
    """Drawable segments, in clock order."""
    return sorted((s for s in segments if is_drawable(s)), key=lambda s: s.start_minute)


# The printed grid resolves to quarter hours. This mirrors the on-screen
# renderer's snapping (frontend/src/lib/logGrid.js) exactly, so the PDF and the
# SVG draw the trace on the same tick boundaries. Snapping affects the DRAWING
# only -- never the totals or any reported number.
TICK_MINUTES = 15


def snap_minute(minute: float) -> int:
    """Nearest quarter-hour, rounding halves up (floor(x + 0.5)) to match the JS."""
    import math

    return int(math.floor(float(minute) / TICK_MINUTES + 0.5)) * TICK_MINUTES


def snap_segments(segments):
    """Snap each segment's drawn span to quarter-hour boundaries.

    Same contract as the on-screen renderer: contiguous (each drawn end is the
    next drawn start) and a minimum one-tick width so a short stop stays visible.
    """
    usable = ordered_segments(segments)
    cursor = None
    out = []
    for segment in usable:
        start = snap_minute(segment.start_minute) if cursor is None else cursor
        end = snap_minute(segment.end_minute)
        if end < start + TICK_MINUTES:
            end = start + TICK_MINUTES
        if end > MINUTES_PER_DAY:
            end = MINUTES_PER_DAY
        if start > MINUTES_PER_DAY - TICK_MINUTES:
            start = MINUTES_PER_DAY - TICK_MINUTES
        cursor = end
        out.append((segment, start, end))
    return out


def build_trace(segments, grid_x, grid_w, grid_top, row_h):
    """Horizontal lines plus the vertical connectors at each status change.

    Drawn positions are snapped to quarter-hour ticks. Coordinates are still
    measured from the top; the caller flips them.
    """
    snapped = snap_segments(segments)

    lines = [
        {
            "status": segment.status,
            "x1": minute_to_x(snap_start, grid_x, grid_w),
            "x2": minute_to_x(snap_end, grid_x, grid_w),
            "y": row_center_from_top(segment.status, grid_top, row_h),
        }
        for segment, snap_start, snap_end in snapped
    ]

    connectors = []
    for (current, _cs, _ce), (following, follow_start, _fe) in zip(snapped, snapped[1:]):
        if current.status == following.status:
            continue
        connectors.append(
            {
                # The shared snapped boundary -- a quarter-hour tick by construction.
                "x": minute_to_x(follow_start, grid_x, grid_w),
                "y1": row_center_from_top(current.status, grid_top, row_h),
                "y2": row_center_from_top(following.status, grid_top, row_h),
            }
        )

    return lines, connectors


def build_remarks(segments, grid_x, grid_w):
    """Location labels, anchored at the same snapped boundary as the connector."""
    return [
        {
            "x": minute_to_x(snap_start, grid_x, grid_w),
            "text": segment.remark.strip(),
        }
        for segment, snap_start, _snap_end in snap_segments(segments)
        if isinstance(getattr(segment, "remark", None), str) and segment.remark.strip()
    ]

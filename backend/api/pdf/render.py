"""Draws the FMCSA driver's daily log onto a reportlab canvas.

One page per log day: draw, showPage(), draw the next, save() at the end.

Coordinates throughout this module are measured from the TOP of the page,
matching the on-screen renderer, and are converted at the moment of drawing by
`y()`. That keeps the mental model consistent with the SVG version and confines
reportlab's bottom-left origin to a single function.

The form prints only what the trip genuinely provides -- day-of-trip, from/to,
miles, the duty trace, the totals and the derivable recap figures. Every identity
field, and the date, is left as an empty box for the driver to complete by hand;
nothing is invented.

Text is ASCII only. ReportLab's built-in fonts have no glyphs for Unicode
subscripts, superscripts or typographic dashes, and render them as black boxes.
"""

from io import BytesIO

from reportlab.pdfgen import canvas as pdf_canvas

from .form import (
    BAND_TOP,
    BOX_BORDER,
    BOX_H,
    CYCLE_LIMIT_HOURS,
    FILING_NOTES,
    FONT,
    FONT_BOLD,
    GRID_BOTTOM,
    GRID_RIGHT,
    GRID_TOP,
    GRID_W,
    GRID_X,
    HAIRLINE,
    INK,
    INSTRUCTION_LINES,
    MARGIN,
    MUTED,
    PAGE_H,
    PAGE_SIZE,
    PAGE_W,
    RECAP_X,
    REMARKS_BOTTOM,
    ROW_H,
    RULE,
    SIZE_GRID_LABEL,
    SIZE_HOUR,
    SIZE_LABEL,
    SIZE_NOTE,
    SIZE_RECAP_LABEL,
    SIZE_RECAP_VALUE,
    SIZE_TITLE,
    SIZE_TOTAL,
    SIZE_VALUE,
    STATUS_COLORS,
    TOTALS_W,
)
from .geometry import (
    ROWS,
    build_remarks,
    build_trace,
    minute_to_x,
    row_center_from_top,
    row_top_from_top,
    to_pdf_y,
)


def y(from_top: float) -> float:
    """Top-left y -> reportlab's bottom-left y."""
    return to_pdf_y(from_top, PAGE_H)


def _hour_label(hour: int) -> str:
    if hour in (0, 24):
        return "Midnight"
    if hour == 12:
        return "Noon"
    return str(hour % 12)


def running_cycle_used(days, current_cycle_used):
    """Per-day running 70-hour/8-day figures.

    The cycle counter is seeded with the hours used before the trip and each day
    adds that day's on-duty time (driving + on-duty-not-driving). So each sheet
    reports its OWN totals -- hours used through the end of that day, and hours
    available the next day -- rather than the end-of-trip figure stamped on every
    page.

    A 34-hour restart zeroes the cycle. It is detected by its persisted remark,
    because the individual restart is not stored as a typed field on the log
    rows; on a restart day the counter resets before that day's on-duty is added.
    Restarts only arise from a very high starting cycle, and the common no-restart
    case is a plain running sum.
    """
    used = float(current_cycle_used)
    result = []
    for day in days:
        segments = list(day.segments.all())
        if any("restart" in (getattr(s, "remark", "") or "").lower() for s in segments):
            used = 0.0
        used += day.total_driving + day.total_on_duty
        available = max(0.0, CYCLE_LIMIT_HOURS - used)
        result.append({"used": round(used, 2), "available": round(available, 2)})
    return result


# --- primitives ------------------------------------------------------------


def _text(c, x, from_top, value, size=SIZE_LABEL, color=INK, font=FONT, anchor="start"):
    c.setFillColorRGB(*color)
    c.setFont(font, size)
    draw = {"start": c.drawString, "middle": c.drawCentredString, "end": c.drawRightString}
    draw[anchor](x, y(from_top), str(value))


def _line(c, x1, top1, x2, top2, color=RULE, width=0.6):
    c.setStrokeColorRGB(*color)
    c.setLineWidth(width)
    c.line(x1, y(top1), x2, y(top2))


def _rect(c, x, top, w, h, color=BOX_BORDER, width=0.8):
    c.setStrokeColorRGB(*color)
    c.setLineWidth(width)
    c.rect(x, y(top + h), w, h, stroke=1, fill=0)


def _wrap(c, text, font, size, max_width):
    """Greedy word wrap using the font's real metrics."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and c.stringWidth(trial, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _box_field(c, x, box_top, w, label, value=None, box_h=BOX_H, value_size=SIZE_VALUE):
    """A captioned box. Prefilled if a value is given, otherwise empty to write in."""
    _text(c, x, box_top - 3, label, size=SIZE_LABEL, color=MUTED)
    _rect(c, x, box_top, w, box_h)
    if value not in (None, ""):
        _text(c, x + 5, box_top + box_h - 5.5, str(value), size=value_size, font=FONT_BOLD)


def _date_field(c, x, box_top, w):
    """Month / day / year as three empty boxes, for the driver to date by hand."""
    _text(c, x, box_top - 3, "DATE (MO / DAY / YEAR)", size=SIZE_LABEL, color=MUTED)
    gap = 16.0
    seg = (w - 2 * gap) / 3
    lefts = [x + i * (seg + gap) for i in range(3)]
    for left in lefts:
        _rect(c, left, box_top, seg, BOX_H)
    for left in lefts[:-1]:
        _text(c, left + seg + gap / 2, box_top + BOX_H - 5.5, "/", size=SIZE_VALUE,
              color=MUTED, anchor="middle")


# --- page ------------------------------------------------------------------


def draw_day(c, trip, day, index, total_days, recap):
    """One complete daily log page. `recap` is this day's running cycle figures."""
    _draw_header(c, trip, day, index, total_days)
    _draw_grid(c, day)
    _draw_trace(c, day)
    _draw_totals(c, day)
    _draw_remark_stems(c, day)
    _draw_shipping_and_instructions(c)
    _draw_recap(c, day, recap)


def _draw_header(c, trip, day, index, total_days):
    right = PAGE_W - MARGIN

    _text(c, MARGIN, 32, "Driver's Daily Log", size=SIZE_TITLE, font=FONT_BOLD)
    _text(c, MARGIN, 46, "(24 hours)", size=SIZE_NOTE, color=MUTED)

    _text(c, right, 26, f"Day {index + 1} of {total_days}", size=SIZE_VALUE,
          font=FONT_BOLD, anchor="end")
    for offset, note in enumerate(FILING_NOTES):
        _text(c, right, 40 + offset * 9, note, size=SIZE_NOTE - 0.5, color=MUTED, anchor="end")

    # Row A -- PREFILLED from the trip.
    miles = f"{day.total_miles:,.0f}"
    _box_field(c, MARGIN, 70, 190, "FROM", trip.current_location)
    _box_field(c, MARGIN + 202, 70, 190, "TO", trip.dropoff_location)
    _box_field(c, MARGIN + 404, 70, 158, "TOTAL MILES DRIVING TODAY", miles)
    _box_field(c, MARGIN + 574, 70, right - (MARGIN + 574), "TOTAL MILEAGE TODAY", miles)

    # Row B -- BLANK (date + carrier + co-driver).
    _date_field(c, MARGIN, 106, 176)
    _box_field(c, MARGIN + 188, 106, 330, "NAME OF CARRIER OR CARRIERS")
    _box_field(c, MARGIN + 530, 106, right - (MARGIN + 530), "CO-DRIVER")

    # Row C -- BLANK (equipment + addresses).
    _box_field(c, MARGIN, 142, 210, "TRACTOR / TRAILER NUMBERS")
    _box_field(c, MARGIN + 222, 142, 270, "MAIN OFFICE ADDRESS")
    _box_field(c, MARGIN + 504, 142, right - (MARGIN + 504), "HOME TERMINAL ADDRESS")

    # Row D -- BLANK (certification).
    _box_field(c, MARGIN, 178, 340, "DRIVER'S SIGNATURE / NAME")
    _text(c, MARGIN + 352, 190, "I certify these entries are true and correct.",
          size=SIZE_NOTE, color=MUTED)


# --- grid ------------------------------------------------------------------


def _draw_grid(c, day):
    grid_right = GRID_X + GRID_W

    for hour in range(25):
        x = minute_to_x(hour * 60, GRID_X, GRID_W)
        if hour < 24:  # closing midnight omitted so it clears the totals caption
            _text(c, x, GRID_TOP - 6, _hour_label(hour), size=SIZE_HOUR, color=MUTED,
                  anchor="middle")

    _text(c, grid_right + TOTALS_W / 2, GRID_TOP - 6, "Total Hours", size=SIZE_HOUR,
          color=MUTED, anchor="middle")

    for index, (status, label) in enumerate(ROWS):
        top = row_top_from_top(index, GRID_TOP, ROW_H)
        centre = row_center_from_top(status, GRID_TOP, ROW_H)

        _text(c, GRID_X - 6, centre + 2.5, label, size=SIZE_GRID_LABEL, anchor="end")

        for hour in range(24):
            for quarter in (15, 30, 45):
                x = minute_to_x(hour * 60 + quarter, GRID_X, GRID_W)
                height = ROW_H * (0.42 if quarter == 30 else 0.24)
                _line(c, x, top + ROW_H, x, top + ROW_H - height, color=HAIRLINE, width=0.4)

    for hour in range(25):
        x = minute_to_x(hour * 60, GRID_X, GRID_W)
        heavy = hour % 6 == 0
        _line(c, x, GRID_TOP, x, GRID_BOTTOM,
              color=RULE if heavy else HAIRLINE, width=0.7 if heavy else 0.4)

    for index in range(5):
        top = GRID_TOP + index * ROW_H
        _line(c, MARGIN, top, grid_right + TOTALS_W, top, color=RULE, width=0.6)
    _line(c, grid_right, GRID_TOP, grid_right, GRID_BOTTOM, color=RULE, width=0.7)
    _line(c, grid_right + TOTALS_W, GRID_TOP, grid_right + TOTALS_W, GRID_BOTTOM,
          color=RULE, width=0.6)
    _line(c, MARGIN, GRID_TOP, MARGIN, GRID_BOTTOM, color=RULE, width=0.6)


def _draw_trace(c, day):
    """The duty trace. Verticals first, so the coloured horizontals sit on top."""
    segments = list(day.segments.all())
    lines, connectors = build_trace(segments, GRID_X, GRID_W, GRID_TOP, ROW_H)

    c.setStrokeColorRGB(*MUTED)
    c.setLineWidth(1.0)
    for connector in connectors:
        c.line(connector["x"], y(connector["y1"]), connector["x"], y(connector["y2"]))

    c.setLineWidth(2.2)
    c.setLineCap(0)
    for line in lines:
        c.setStrokeColorRGB(*STATUS_COLORS[line["status"]])
        c.line(line["x1"], y(line["y"]), line["x2"], y(line["y"]))


def _draw_totals(c, day):
    """Straight from the stored row totals -- never recomputed from segments."""
    stored = {
        "off_duty": day.total_off_duty,
        "sleeper": day.total_sleeper,
        "driving": day.total_driving,
        "on_duty": day.total_on_duty,
    }
    x = GRID_X + GRID_W + TOTALS_W / 2
    for status, _label in ROWS:
        centre = row_center_from_top(status, GRID_TOP, ROW_H)
        _text(c, x, centre + 3, f"{stored[status]:.2f}", size=SIZE_TOTAL,
              font=FONT_BOLD, anchor="middle")

    total = sum(stored.values())
    _text(c, x, GRID_BOTTOM + 12, f"{total:.2f}", size=SIZE_TOTAL, font=FONT_BOLD,
          anchor="middle")
    _text(c, x, GRID_BOTTOM + 21, "TOTAL", size=SIZE_HOUR - 1, color=MUTED, anchor="middle")


def _draw_remark_stems(c, day):
    """No location text -- just a stem at each duty-status change for the driver
    to hand-write the location beside. Stems stay on the snapped boundaries the
    trace connectors use, via build_remarks."""
    _text(c, MARGIN, GRID_BOTTOM + 12, "REMARKS", size=SIZE_LABEL, font=FONT_BOLD, color=MUTED)
    _line(c, MARGIN, REMARKS_BOTTOM, GRID_RIGHT, REMARKS_BOTTOM, color=RULE, width=0.6)

    for remark in build_remarks(list(day.segments.all()), GRID_X, GRID_W):
        _line(c, remark["x"], GRID_BOTTOM, remark["x"], REMARKS_BOTTOM - 4,
              color=HAIRLINE, width=0.5)


# --- band below the grid ---------------------------------------------------


def _draw_shipping_and_instructions(c):
    """Left of the band: shipping-document boxes (blank) and the instructions."""
    left = MARGIN
    region_w = RECAP_X - MARGIN - 18

    _text(c, left, BAND_TOP, "SHIPPING DOCUMENTS", size=SIZE_LABEL, font=FONT_BOLD)

    box_top = BAND_TOP + 12
    _box_field(c, left, box_top, 196, "DVL OR MANIFEST NO.")
    _box_field(c, left + 208, box_top, region_w - 208, "SHIPPER & COMMODITY")

    top = box_top + BOX_H + 14
    for line in INSTRUCTION_LINES:
        for wrapped in _wrap(c, line, FONT, SIZE_NOTE, region_w):
            _text(c, left, top, wrapped, size=SIZE_NOTE, color=MUTED)
            top += 10
        top += 2


def _draw_recap(c, day, recap):
    """The recap block. Derivable figures are prefilled; everything the
    single-cycle model cannot derive is an empty box, like the other blanks --
    no invented numbers and no 'N/A' string on the printable form."""
    on_duty_today = day.total_driving + day.total_on_duty

    _text(c, RECAP_X, BAND_TOP, "RECAP", size=SIZE_LABEL, font=FONT_BOLD)
    _text(c, RECAP_X + 40, BAND_TOP, "Complete at end of day", size=SIZE_NOTE - 0.5,
          color=MUTED)

    _box_field(c, RECAP_X, BAND_TOP + 12, 150, "ON DUTY HOURS TODAY (LINES 3 + 4)",
               f"{on_duty_today:.2f}", box_h=15, value_size=SIZE_RECAP_VALUE)

    col_w = (GRID_RIGHT - RECAP_X) / 2
    # value=None renders an empty box for the driver to complete by hand.
    columns = [
        (
            "70 Hour / 8 Day Drivers",
            [
                ("A. On duty last 8 days incl. today", f"{recap['used']:.2f}"),
                ("B. Available tomorrow (70 - A)", f"{recap['available']:.2f}"),
                ("C. On duty last 5 days incl. today", None),
            ],
        ),
        (
            "60 Hour / 7 Day Drivers",
            [
                ("A. On duty last 7 days incl. today", None),
                ("B. Available tomorrow (60 - A)", None),
                ("C. On duty last 7 days incl. today", None),
            ],
        ),
    ]

    header_top = BAND_TOP + 40
    for col_index, (title, boxes) in enumerate(columns):
        x = RECAP_X + col_index * col_w
        _text(c, x, header_top, title, size=SIZE_RECAP_LABEL, font=FONT_BOLD, color=MUTED)
        _line(c, x, header_top + 3, x + col_w - 10, header_top + 3, color=HAIRLINE, width=0.4)
        for box_index, (label, value) in enumerate(boxes):
            box_top = header_top + 20 + box_index * 22
            _text(c, x, box_top - 3, label, size=SIZE_RECAP_LABEL - 1.4, color=MUTED)
            _rect(c, x, box_top, col_w - 14, 13)
            if value is not None:
                _text(c, x + 4, box_top + 8.5, value, size=SIZE_RECAP_VALUE, font=FONT_BOLD)

    note_top = header_top + 20 + 3 * 22 + 2
    _text(c, RECAP_X, note_top,
          "*If you took 34 consecutive hours off duty you have 60/70 hours available.",
          size=SIZE_NOTE - 1.4, color=MUTED)

    _text(c, MARGIN, PAGE_H - MARGIN - 6,
          "70 hour / 8 day cycle, property-carrying driver. "
          "Driving time computed at 55 mph from routed distance.",
          size=SIZE_NOTE - 1, color=MUTED)


# --- document --------------------------------------------------------------


def build_log_pdf(trip) -> bytes:
    """A multi-page PDF: one page per persisted log day."""
    buffer = BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    c.setTitle(f"Driver's Daily Log - trip {trip.id}")
    c.setAuthor("ELD Trip Planner")

    days = list(trip.logs.all())
    recap = running_cycle_used(days, trip.current_cycle_used)
    for index, day in enumerate(days):
        draw_day(c, trip, day, index, len(days), recap[index])
        c.showPage()

    if not days:
        # An empty document is still a valid PDF; a trip with no log days should
        # download something readable rather than a corrupt file.
        _text(c, MARGIN, 60, "This trip produced no log days.", size=10)
        c.showPage()

    c.save()
    return buffer.getvalue()

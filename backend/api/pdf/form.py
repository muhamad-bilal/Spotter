"""Layout constants for the printable daily log.

The PDF prints only what the app genuinely derives from the trip -- the date is
NOT among these; it is left for the driver -- and leaves every identity field
(carrier, addresses, equipment, driver, shipping documents) as an empty box for
the driver to complete by hand. Nothing is invented, so there are no placeholder
identity values here.

Prefilled from the trip: day-of-trip, from/to, miles, the duty trace, the totals
column, and the recap figures the single-cycle model can derive. Everything else
prints as an empty box.
"""

from reportlab.lib.pagesizes import letter

# Kept only so a test can assert this phrase is ABSENT from the printable PDF
# (it belongs on the on-screen sheet, not the form the driver signs).
NO_HISTORY_NOTE = "N/A - single-trip simulation"

# The FMCSA cycle. Used for the running recap arithmetic (70 - hours used).
CYCLE_LIMIT_HOURS = 70

FILING_NOTES = [
    "Original - File at home terminal.",
    "Duplicate - Driver retains in his/her possession for 8 days.",
]

INSTRUCTION_LINES = [
    "Enter name of place you reported and where released from work and when "
    "and where each change of duty occurred.",
    "Use time standard of home terminal.",
]

# --- page ------------------------------------------------------------------

PAGE_W, PAGE_H = letter[1], letter[0]  # landscape letter: 792 x 612
PAGE_SIZE = (PAGE_W, PAGE_H)

MARGIN = 28.0

# --- grid ------------------------------------------------------------------
# Measured from the TOP of the page; geometry.to_pdf_y does the flip.

LABEL_W = 118.0
TOTALS_W = 56.0
GRID_X = MARGIN + LABEL_W
GRID_W = PAGE_W - (2 * MARGIN) - LABEL_W - TOTALS_W

GRID_TOP = 214.0
ROW_H = 27.0
GRID_H = ROW_H * 4
GRID_BOTTOM = GRID_TOP + GRID_H
GRID_RIGHT = GRID_X + GRID_W + TOTALS_W

# Remarks strip. The location labels are no longer printed -- only a stem drops
# from the grid at each duty-status change, and the driver hand-writes the
# location beside it. So the band just needs writing room, not the tall clearance
# the angled labels used to require.
REMARKS_H = 50.0
REMARKS_BOTTOM = GRID_BOTTOM + REMARKS_H

# Below the remarks: shipping documents + instructions on the left, the recap
# grid on the right, matching the real form's layout.
BAND_TOP = REMARKS_BOTTOM + 14.0
RECAP_X = 470.0  # left edge of the recap block

# --- type ------------------------------------------------------------------
# Bigger and bolder than before so the printed form is comfortably legible.

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

SIZE_TITLE = 17
SIZE_LABEL = 7.2       # field captions
SIZE_VALUE = 10.5      # prefilled values
SIZE_GRID_LABEL = 7.6  # row captions
SIZE_HOUR = 6.6        # hour headers
SIZE_TOTAL = 9.5       # totals column
SIZE_RECAP_LABEL = 6.6
SIZE_RECAP_VALUE = 9
SIZE_NOTE = 7          # instructions, filing notice

# --- boxes -----------------------------------------------------------------

BOX_H = 17.0           # height of a hand-fill box; roomy enough to write in
BOX_BORDER = (0.45, 0.47, 0.5)

# --- ink -------------------------------------------------------------------

RULE = (0.28, 0.29, 0.32)
HAIRLINE = (0.66, 0.66, 0.70)
INK = (0.04, 0.05, 0.07)
MUTED = (0.36, 0.38, 0.42)

# The same duty palette as the app, so the printout and the screen agree.
STATUS_COLORS = {
    "off_duty": (0.39, 0.45, 0.55),
    "sleeper": (0.43, 0.36, 0.82),
    "driving": (0.85, 0.47, 0.02),
    "on_duty": (0.15, 0.39, 0.92),
}

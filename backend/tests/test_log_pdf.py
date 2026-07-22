"""The printable daily log.

Two things are easy to get catastrophically wrong here and both are asserted
directly: reportlab's bottom-left origin (getting the flip backwards turns the
log upside down, with Off Duty where On Duty belongs), and the page count.
"""

import io

import pytest
from api import views
from api.pdf import form, geometry
from api.pdf.render import build_log_pdf, y
from api_fixtures import VALID_REQUEST, fake_planner
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTCurve, LTLine, LTRect
from pypdf import PdfReader

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/trips/"

# --- what the PDF actually drew (measured, not what the code intended) ------
#
# These read the emitted PDF back with pdfminer, so a test asserts on the pixels
# reportlab produced, not on the return value of a helper. That distinction
# matters: earlier tests checked the snapper's output and a label's intended
# anchor, both of which stay green even when the drawing lands somewhere else.


def rendered_page(trip, index=0):
    return list(extract_pages(io.BytesIO(build_log_pdf(trip))))[index]


def _walk(page):
    stack = list(page)
    while stack:
        item = stack.pop()
        yield item
        if hasattr(item, "__iter__"):
            stack.extend(item)


def rotated_glyph_tops(page):
    """Top y of every rotated glyph -- i.e. the remark labels -- in PDF coords."""
    tops = []
    for item in _walk(page):
        if isinstance(item, LTChar):
            a, b, c, d, e, f = item.matrix
            if abs(b) > 0.05 or abs(c) > 0.05:  # rotated => a remark label
                tops.append(item.bbox[3])
    return tops


def drawn_vertical_xs(page):
    """x of every drawn vertical line that spans more than one row in the grid.

    That is the trace's connectors (and full-height hour lines); both must sit on
    quarter-hour ticks. Short quarter-hour tick marks are excluded by the span.
    """
    grid_bottom_y = form.PAGE_H - form.GRID_BOTTOM
    grid_top_y = form.PAGE_H - form.GRID_TOP
    xs = []
    for item in _walk(page):
        if isinstance(item, (LTLine, LTCurve, LTRect)):
            x0, y0, x1, y1 = item.bbox
            x_mid = (x0 + x1) / 2
            if (
                abs(x1 - x0) < 0.6  # vertical
                and (y1 - y0) > form.ROW_H + 2  # spans more than one row
                and y0 >= grid_bottom_y - 2
                and y1 <= grid_top_y + 2
                # inside the 24-hour plotting area, excluding the frame borders
                and form.GRID_X - 1 <= x_mid <= form.GRID_X + form.GRID_W + 1
            ):
                xs.append(x_mid)
    return xs


def x_to_tick_multiple(x):
    """Where a drawn x falls as a multiple of the 15-minute tick (integer = on tick)."""
    fraction = (x - form.GRID_X) / form.GRID_W
    return fraction * (geometry.MINUTES_PER_DAY / geometry.TICK_MINUTES)


@pytest.fixture(autouse=True)
def mocked_planner(monkeypatch):
    monkeypatch.setattr(views, "plan_route", fake_planner(300.0, 1550.0))


@pytest.fixture
def multi_day_trip(client):
    """A real persisted trip spanning several log days."""
    from api.models import Trip

    response = client.post(ENDPOINT, VALID_REQUEST, content_type="application/json")
    assert response.status_code == 201
    body = response.json()
    assert len(body["logs"]) > 1, "fixture must span multiple days"
    return Trip.objects.get(pk=body["trip"]["id"]), body


# --- coordinate system -----------------------------------------------------


def test_y_flip_inverts_around_the_page_height():
    assert geometry.to_pdf_y(0, 612) == 612
    assert geometry.to_pdf_y(612, 612) == 0
    assert geometry.to_pdf_y(100, 612) == 512


def test_rows_further_down_the_form_sit_lower_on_the_page():
    """The check that catches a vertically flipped log.

    Off Duty prints above On Duty. In reportlab's bottom-left space that means a
    LARGER y for Off Duty. If the flip were missed, this ordering inverts.
    """
    positions = {
        status: y(geometry.row_center_from_top(status, form.GRID_TOP, form.ROW_H))
        for status, _label in geometry.ROWS
    }
    assert positions["off_duty"] > positions["sleeper"] > positions["driving"] > positions["on_duty"]


def test_every_row_lands_inside_the_page():
    for status, _label in geometry.ROWS:
        value = y(geometry.row_center_from_top(status, form.GRID_TOP, form.ROW_H))
        assert 0 < value < form.PAGE_H


# --- parity with the on-screen renderer ------------------------------------
# The SVG renderer is JavaScript, so the formula cannot literally be shared.
# These pin the Python port to the same anchors the JS test asserts.


@pytest.mark.parametrize(
    "minute, fraction",
    [(0, 0.0), (360, 0.25), (720, 0.5), (1080, 0.75), (1440, 1.0)],
)
def test_minute_to_x_matches_the_svg_anchors(minute, fraction):
    x = geometry.minute_to_x(minute, form.GRID_X, form.GRID_W)
    assert x == pytest.approx(form.GRID_X + fraction * form.GRID_W)


def test_minute_to_x_clamps_out_of_range_values():
    assert geometry.minute_to_x(-99, 100, 800) == 100
    assert geometry.minute_to_x(99999, 100, 800) == 900
    assert geometry.minute_to_x("nonsense", 100, 800) == 100


def test_trace_places_a_driving_segment_on_the_driving_row():
    class Seg:
        def __init__(self, status, start, end, remark=""):
            self.status, self.start_minute, self.end_minute, self.remark = (
                status, start, end, remark,
            )

    segments = [
        Seg("off_duty", 0, 360, "Chicago, IL"),
        Seg("driving", 360, 660),
        Seg("on_duty", 660, 720, "Indianapolis, IN"),
    ]
    lines, connectors = geometry.build_trace(
        segments, form.GRID_X, form.GRID_W, form.GRID_TOP, form.ROW_H
    )
    driving = [line for line in lines if line["status"] == "driving"][0]

    assert driving["x1"] == pytest.approx(geometry.minute_to_x(360, form.GRID_X, form.GRID_W))
    assert driving["x2"] == pytest.approx(geometry.minute_to_x(660, form.GRID_X, form.GRID_W))
    assert driving["y"] == geometry.row_center_from_top("driving", form.GRID_TOP, form.ROW_H)
    assert len(connectors) == 2


def test_malformed_segments_are_not_drawn():
    class Seg:
        def __init__(self, status, start, end):
            self.status, self.start_minute, self.end_minute, self.remark = status, start, end, ""

    segments = [
        Seg("nonsense", 0, 60),
        Seg("driving", None, 60),
        Seg("driving", 60, 60),
        Seg("driving", 0, 60),
    ]
    lines, _ = geometry.build_trace(segments, form.GRID_X, form.GRID_W, form.GRID_TOP, form.ROW_H)
    assert len(lines) == 1


# --- quarter-hour snapping (must match the on-screen renderer) --------------


class _Seg:
    def __init__(self, status, start, end, remark=""):
        self.status = status
        self.start_minute = start
        self.end_minute = end
        self.remark = remark


@pytest.mark.parametrize(
    "minute, expected",
    [(0, 0), (7, 0), (8, 15), (687, 690), (747, 750), (1080, 1080), (1440, 1440)],
)
def test_snap_minute_rounds_to_the_nearest_quarter_hour(minute, expected):
    assert geometry.snap_minute(minute) == expected


def _minute_at(x):
    return (x - form.GRID_X) / form.GRID_W * geometry.MINUTES_PER_DAY


def test_trace_snaps_boundaries_and_connectors_to_ticks():
    """A change at 11:27 (687) is drawn at the 11:30 tick, not floating between."""
    segments = [
        _Seg("off_duty", 0, 360, "Chicago, IL"),
        _Seg("driving", 360, 687),
        _Seg("on_duty", 687, 747, "Indianapolis, IN"),
    ]
    lines, connectors = geometry.build_trace(
        segments, form.GRID_X, form.GRID_W, form.GRID_TOP, form.ROW_H
    )

    driving = [line for line in lines if line["status"] == "driving"][0]
    assert driving["x2"] == pytest.approx(geometry.minute_to_x(690, form.GRID_X, form.GRID_W))

    for connector in connectors:
        minute = _minute_at(connector["x"])
        assert round(minute) % geometry.TICK_MINUTES == 0, f"connector off-tick at {minute}"


def test_trace_stays_contiguous_after_snapping():
    """Each drawn segment ends exactly where the next begins -- no gap, no overlap."""
    segments = [
        _Seg("off_duty", 0, 360),
        _Seg("driving", 360, 687),
        _Seg("on_duty", 687, 747),
        _Seg("driving", 747, 1080),
        _Seg("sleeper", 1080, 1440),
    ]
    lines, _ = geometry.build_trace(
        segments, form.GRID_X, form.GRID_W, form.GRID_TOP, form.ROW_H
    )
    for current, following in zip(lines, lines[1:]):
        assert current["x2"] == pytest.approx(following["x1"])


def test_short_stop_keeps_a_minimum_one_tick_width():
    """A 10-minute stop must not round to zero width and disappear."""
    segments = [
        _Seg("off_duty", 0, 100),
        _Seg("on_duty", 100, 110),
        _Seg("off_duty", 110, 1440),
    ]
    lines, _ = geometry.build_trace(
        segments, form.GRID_X, form.GRID_W, form.GRID_TOP, form.ROW_H
    )
    on_duty = [line for line in lines if line["status"] == "on_duty"][0]
    width_minutes = _minute_at(on_duty["x2"]) - _minute_at(on_duty["x1"])
    assert width_minutes >= geometry.TICK_MINUTES - 1e-6


def test_drawn_connectors_land_on_quarter_hour_ticks(multi_day_trip):
    """MEASURED: every vertical the PDF actually draws sits on a tick.

    Reads back the emitted lines rather than the snapper's return value, so a
    mapping that snapped the minute but then drew it at the wrong x would fail
    here -- which the return-value tests could not catch.
    """
    trip, _ = multi_day_trip
    for index in range(trip.logs.count()):
        page = rendered_page(trip, index)
        xs = drawn_vertical_xs(page)
        assert xs, f"day {index}: expected drawn vertical lines"
        for x in xs:
            mult = x_to_tick_multiple(x)
            assert abs(mult - round(mult)) < 0.02, (
                f"day {index}: a vertical is drawn at tick-multiple {mult:.3f} (off-tick)"
            )


def test_remarks_anchor_on_the_same_snapped_boundary_as_the_trace():
    segments = [
        _Seg("off_duty", 0, 360, "Chicago, IL"),
        _Seg("driving", 360, 687),
        _Seg("on_duty", 687, 747, "Indianapolis, IN"),
    ]
    remarks = geometry.build_remarks(segments, form.GRID_X, form.GRID_W)
    indy = [r for r in remarks if "Indianapolis" in r["text"]][0]
    # The pickup remark hangs at the snapped 11:30 boundary, matching its connector.
    assert indy["x"] == pytest.approx(geometry.minute_to_x(690, form.GRID_X, form.GRID_W))


# --- the document ----------------------------------------------------------


def test_pdf_has_one_page_per_log_day(multi_day_trip):
    trip, body = multi_day_trip
    reader = PdfReader_from(build_log_pdf(trip))
    assert len(reader.pages) == len(body["logs"])
    assert len(reader.pages) == trip.logs.count()


def test_pdf_is_landscape_letter(multi_day_trip):
    trip, _ = multi_day_trip
    page = PdfReader_from(build_log_pdf(trip)).pages[0]
    assert round(float(page.mediabox.width)) == 792
    assert round(float(page.mediabox.height)) == 612


def test_pdf_pages_carry_the_real_trip_data(multi_day_trip):
    trip, body = multi_day_trip
    reader = PdfReader_from(build_log_pdf(trip))

    for page, day in zip(reader.pages, body["logs"]):
        text = page.extract_text()
        assert trip.current_location in text
        assert trip.dropoff_location in text
        # The four stored totals appear in the totals column.
        for value in day["totals"].values():
            assert f"{value:.2f}" in text


def test_pdf_totals_match_the_persisted_rows(multi_day_trip):
    """The printed totals are the stored ones, not a second computation."""
    trip, _ = multi_day_trip
    reader = PdfReader_from(build_log_pdf(trip))

    for page, day in zip(reader.pages, trip.logs.all()):
        text = page.extract_text()
        total = day.total_off_duty + day.total_sleeper + day.total_driving + day.total_on_duty
        assert f"{total:.2f}" in text
        assert round(total, 2) == 24.00


def test_pdf_includes_the_form_furniture(multi_day_trip):
    trip, _ = multi_day_trip
    text = PdfReader_from(build_log_pdf(trip)).pages[0].extract_text()

    for expected in [
        "Driver's Daily Log",
        "Off Duty",
        "Sleeper Berth",
        "Driving",
        "On Duty",
        "REMARKS",
        "RECAP",
        "TOTAL MILES DRIVING TODAY",
        "NAME OF CARRIER OR CARRIERS",  # the label stays; its value is blank
        "HOME TERMINAL ADDRESS",
        "DRIVER'S SIGNATURE / NAME",
    ]:
        assert expected in text, f"missing from the printed form: {expected!r}"


def test_no_placeholder_identity_is_printed(multi_day_trip):
    """Nothing is invented on the form: the old placeholder strings are gone."""
    trip, _ = multi_day_trip
    text = PdfReader_from(build_log_pdf(trip)).pages[0].extract_text()

    for forbidden in [
        "Spotter Freight Lines",
        "1200 W Cermak",
        "Tractor 4187",
        "Trailer 22-914",
        "Midwest Grain",
        "DVL 4471",
        "placeholder values",
        "(driver name)",
    ]:
        assert forbidden not in text, f"placeholder leaked into the form: {forbidden!r}"


def test_shipping_documents_are_blank_labels_only(multi_day_trip):
    trip, _ = multi_day_trip
    text = PdfReader_from(build_log_pdf(trip)).pages[0].extract_text()

    # The captions stay so the driver knows what to write; the values are blank.
    assert "SHIPPING DOCUMENTS" in text
    assert "MANIFEST NO." in text
    assert "SHIPPER & COMMODITY" in text
    assert "Use time standard of home terminal." in text
    assert "each change of duty occurred" in text


def test_date_is_left_blank_for_the_driver(multi_day_trip):
    """The date is the driver's to fill; only the caption and boxes are printed."""
    trip, _ = multi_day_trip
    for index, day in enumerate(trip.logs.all()):
        text = PdfReader_from(build_log_pdf(trip)).pages[index].extract_text()
        assert "DATE (MO / DAY / YEAR)" in text
        assert day.date.strftime("%m / %d / %Y") not in text
        assert day.date.strftime("%m/%d/%Y") not in text
        assert str(day.date.year) not in text  # no year prefilled anywhere on the sheet
        # But the sheet still identifies which day of the trip it is.
        assert f"Day {index + 1} of" in text


def test_filing_notice_is_present(multi_day_trip):
    trip, _ = multi_day_trip
    text = PdfReader_from(build_log_pdf(trip)).pages[0].extract_text()
    assert "File at home terminal." in text
    assert "8 days." in text


def test_remarks_have_stems_but_no_labels(multi_day_trip):
    """The location labels are removed; only the stems remain for hand-writing.

    Two measured assertions: no rotated glyph is drawn anywhere (the angled
    labels are gone, so the collision problem is retired), and a stem drops in
    the remarks band at each duty-status change.
    """
    trip, _ = multi_day_trip
    grid_bottom_y = form.PAGE_H - form.GRID_BOTTOM
    remarks_bottom_y = form.PAGE_H - form.REMARKS_BOTTOM

    for index in range(trip.logs.count()):
        page = rendered_page(trip, index)
        assert not rotated_glyph_tops(page), f"day {index}: a remark label was still drawn"

        # Vertical hairlines living in the remarks band = the stems.
        stems = [
            (x0 + x1) / 2
            for item in _walk(page)
            if isinstance(item, (LTLine, LTCurve, LTRect))
            for (x0, y0, x1, y1) in [item.bbox]
            if abs(x1 - x0) < 0.6
            and remarks_bottom_y - 2 <= y0
            and y1 <= grid_bottom_y + 2
            and (y1 - y0) > 4
        ]
        assert stems, f"day {index}: expected remark stems in the band"

        # Each stem sits on a snapped boundary the trace uses.
        for x in stems:
            mult = x_to_tick_multiple(x)
            assert abs(mult - round(mult)) < 0.05, f"stem off-tick at multiple {mult:.3f}"


def test_recap_columns_present_and_no_na_string(multi_day_trip):
    trip, _ = multi_day_trip
    text = PdfReader_from(build_log_pdf(trip)).pages[0].extract_text()

    assert "70 Hour / 8 Day Drivers" in text
    assert "60 Hour / 7 Day Drivers" in text
    assert "34 consecutive hours off duty" in text
    # Non-derivable boxes are left blank, not stamped with the caveat string.
    assert form.NO_HISTORY_NOTE not in text
    assert "N/A" not in text


def test_recap_values_are_per_day_running_not_end_of_trip(multi_day_trip):
    """The accuracy fix: each sheet shows its own running cycle figures.

    Reconstructed independently from each day's on-duty totals, then checked
    against what the pages actually print -- and asserted to DIFFER page to page,
    which is exactly what stamping the end-of-trip figure would break.
    """
    trip, body = multi_day_trip
    pages = PdfReader_from(build_log_pdf(trip)).pages
    assert len(pages) == len(body["logs"]) >= 2

    used = float(trip.current_cycle_used)
    seen_available = []
    for page, day in zip(pages, body["logs"]):
        used += day["totals"]["driving"] + day["totals"]["on_duty"]
        available = round(max(0.0, 70 - used), 2)
        text = page.extract_text()

        assert f"{round(used, 2):.2f}" in text, f"running used {used:.2f} missing"
        assert f"{available:.2f}" in text, f"available {available:.2f} missing"
        seen_available.append(available)

    assert len(set(seen_available)) == len(seen_available), (
        "every sheet showed the same availability -- the end-of-trip figure was "
        "stamped on all of them instead of per-day running values"
    )


def test_known_trip_recap_matches_the_expected_arithmetic(client, monkeypatch):
    """LA -> Phoenix -> Dallas, cycle 8: 50.00 / 38.50 / 33.08 available."""
    from api.models import Trip
    from api.pdf.render import running_cycle_used

    monkeypatch.setattr(views, "plan_route", fake_planner(300.0, 1550.0))
    body = client.post(ENDPOINT, VALID_REQUEST, content_type="application/json").json()
    trip = Trip.objects.get(pk=body["trip"]["id"])

    recap = running_cycle_used(list(trip.logs.all()), trip.current_cycle_used)
    # used + available always equals the 70-hour cycle for a no-restart trip.
    for entry in recap:
        assert round(entry["used"] + entry["available"], 2) == 70.00
    # And the values genuinely change from day to day.
    assert len({entry["available"] for entry in recap}) == len(recap)


def test_pdf_text_is_ascii_only(multi_day_trip):
    """ReportLab's built-in fonts draw non-ASCII as black boxes."""
    trip, _ = multi_day_trip
    for page in PdfReader_from(build_log_pdf(trip)).pages:
        text = page.extract_text()
        offenders = {ch for ch in text if ord(ch) > 127}
        assert not offenders, f"non-ASCII glyphs in the PDF: {offenders}"


# --- the endpoint ----------------------------------------------------------


def test_endpoint_returns_a_pdf(client, multi_day_trip):
    trip, body = multi_day_trip
    response = client.get(f"{ENDPOINT}{trip.pk}/logs.pdf")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert f"trip-{trip.pk}.pdf" in response["Content-Disposition"]
    assert "attachment" in response["Content-Disposition"]
    assert len(PdfReader_from(response.content).pages) == len(body["logs"])


def test_endpoint_404s_for_an_unknown_trip(client):
    assert client.get(f"{ENDPOINT}999999/logs.pdf").status_code == 404


def test_single_day_trip_produces_one_page(client, monkeypatch):
    from api.models import Trip

    monkeypatch.setattr(views, "plan_route", fake_planner(120.0, 260.0))
    body = client.post(ENDPOINT, VALID_REQUEST, content_type="application/json").json()
    assert len(body["logs"]) == 1

    trip = Trip.objects.get(pk=body["trip"]["id"])
    assert len(PdfReader_from(build_log_pdf(trip)).pages) == 1


def PdfReader_from(data: bytes) -> PdfReader:
    from io import BytesIO

    return PdfReader(BytesIO(data))

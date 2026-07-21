"""Nominatim wrapper. No test here touches the network."""

import pytest
import requests
import responses
from service_fixtures import NOMINATIM_MISS, NOMINATIM_URL, nominatim_hit

from services import AddressNotFound, GeocodingError, NominatimGeocoder
from services import geocoding as geocoding_module


@pytest.fixture
def geocoder():
    """A geocoder with its own cache, so tests cannot leak results into each other."""
    return NominatimGeocoder(cache={}, user_agent="eld-trip-planner/test")


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    """Neutralise the 1 req/sec throttle so the suite stays fast.

    test_throttle_waits_a_second_between_requests re-instruments it deliberately.
    """
    monkeypatch.setattr(geocoding_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(geocoding_module, "_last_request_at", 0.0)


@responses.activate
def test_resolves_an_address(geocoder):
    responses.get(NOMINATIM_URL, json=nominatim_hit("Chicago, IL"))
    place = geocoder.geocode("Chicago, IL")
    assert (place.latitude, place.longitude) == (41.8755616, -87.6244212)
    assert place.label == "Chicago, IL"


@responses.activate
def test_sends_a_descriptive_user_agent(geocoder):
    """Nominatim's usage policy blocks requests without one."""
    responses.get(NOMINATIM_URL, json=nominatim_hit("Chicago, IL"))
    geocoder.geocode("Chicago, IL")
    assert responses.calls[0].request.headers["User-Agent"] == "eld-trip-planner/test"


@responses.activate
def test_unresolvable_address_raises_with_the_field_name(geocoder):
    responses.get(NOMINATIM_URL, json=NOMINATIM_MISS)
    with pytest.raises(AddressNotFound) as exc:
        geocoder.geocode("asdfqwerzxcv", field="pickup location")
    assert "pickup location" in str(exc.value)
    assert "asdfqwerzxcv" in str(exc.value)


@responses.activate
def test_blank_address_raises_without_calling_the_provider(geocoder):
    with pytest.raises(AddressNotFound):
        geocoder.geocode("   ", field="dropoff location")
    assert len(responses.calls) == 0


@responses.activate
def test_repeated_lookups_are_cached(geocoder):
    responses.get(NOMINATIM_URL, json=nominatim_hit("Chicago, IL"))
    first = geocoder.geocode("Chicago, IL")
    second = geocoder.geocode("chicago, il")  # different case, same place
    assert first == second
    assert len(responses.calls) == 1, "second lookup should not hit the network"


@responses.activate
def test_provider_http_error_raises_geocoding_error(geocoder):
    responses.get(NOMINATIM_URL, status=503)
    with pytest.raises(GeocodingError):
        geocoder.geocode("Chicago, IL")


@responses.activate
def test_unreachable_provider_raises_geocoding_error(geocoder):
    responses.get(NOMINATIM_URL, body=requests.ConnectionError("boom"))
    with pytest.raises(GeocodingError, match="Could not reach"):
        geocoder.geocode("Chicago, IL")


@responses.activate
def test_timeout_raises_geocoding_error(geocoder):
    responses.get(NOMINATIM_URL, body=requests.Timeout("slow"))
    with pytest.raises(GeocodingError, match="Could not reach"):
        geocoder.geocode("Chicago, IL")


@responses.activate
def test_malformed_payload_raises_geocoding_error(geocoder):
    responses.get(NOMINATIM_URL, json=[{"display_name": "no coordinates here"}])
    with pytest.raises(GeocodingError):
        geocoder.geocode("Chicago, IL")


@responses.activate
def test_throttle_waits_a_second_between_requests(geocoder, monkeypatch):
    """Nominatim allows at most one request per second."""
    slept = []
    clock = iter([0.0, 0.0, 0.2, 0.2])  # second call comes 0.2s after the first
    monkeypatch.setattr(geocoding_module.time, "sleep", slept.append)
    monkeypatch.setattr(geocoding_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(geocoding_module, "_last_request_at", 0.0)

    responses.get(NOMINATIM_URL, json=nominatim_hit("Chicago, IL"))
    responses.get(NOMINATIM_URL, json=nominatim_hit("Columbus, OH"))
    geocoder.geocode("Chicago, IL")
    geocoder.geocode("Columbus, OH")

    assert slept, "expected the throttle to sleep before the second request"
    assert slept[-1] == pytest.approx(0.8), "should wait out the remainder of the second"

import json

import pytest

from hardware.generic_client import SpoolioHardwareClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_generic_client_encodes_identifiers_and_protects_the_device_key():
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return FakeResponse({"status": "ok"})

    client = SpoolioHardwareClient(
        "https://spoolio.example",
        "device-secret",
        timeout=3,
        opener=opener,
    )
    assert client.lookup("tag /?") == {"status": "ok"}

    request, timeout = requests.pop()
    assert request.full_url == (
        "https://spoolio.example/api/hardware/spool/tag%20%2F%3F"
    )
    assert request.get_header("Authorization") == "Bearer device-secret"
    assert "device-secret" not in request.full_url
    assert timeout == 3


def test_generic_client_posts_gross_weight_and_events():
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return FakeResponse({"status": "ok"})

    client = SpoolioHardwareClient(
        "http://localhost:8000/",
        "device-secret",
        opener=opener,
    )
    client.update_weight("tag-1", 912.4)
    client.event(
        "stable_weight",
        identifier="tag-1",
        weight=912.4,
        message="settled",
    )

    weight_request, event_request = requests
    assert weight_request.method == "POST"
    assert json.loads(weight_request.data) == {
        "nfc_tag_id": "tag-1",
        "weight": 912.4,
    }
    assert json.loads(event_request.data) == {
        "event_type": "stable_weight",
        "nfc_tag_id": "tag-1",
        "weight": 912.4,
        "message": "settled",
    }


def test_generic_client_rejects_remote_cleartext_by_default():
    with pytest.raises(ValueError, match="HTTP exposes the device key"):
        SpoolioHardwareClient("http://spoolio.example", "device-secret")

    client = SpoolioHardwareClient(
        "http://spoolio.example",
        "device-secret",
        allow_insecure_http=True,
    )
    assert client.base_url == "http://spoolio.example"


@pytest.mark.parametrize("reading", [float("nan"), float("inf"), float("-inf")])
def test_generic_client_rejects_non_finite_readings(reading):
    client = SpoolioHardwareClient("http://localhost:8000", "device-secret")

    with pytest.raises(ValueError, match="must be finite"):
        client.update_weight("tag-1", reading)
    with pytest.raises(ValueError, match="must be finite"):
        client.event("stable_weight", weight=reading)

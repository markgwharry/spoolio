# Spoolio Hardware Protocol v1

Protocol v1 is the small, board-neutral HTTP contract used by Spoolio scales.
The maintained Arduino sketches are examples, not requirements: a client can
run on any MCU, SBC, desktop, or automation system that can make HTTPS requests
and preserve a device API key.

## Compatibility promise

Within Protocol v1, existing fields and meanings will not be removed or changed
incompatibly. New response fields and endpoints may be added. Clients must
ignore response fields they do not understand. The authenticated heartbeat
advertises the active protocol version and measurement semantics.

## Provisioning and authentication

1. Create the owner account and at least one spool in Spoolio.
2. Register a device from the Hardware page. `hardware_type` is descriptive;
   it does not restrict the board or sensor.
3. Copy the device API key when it is displayed. Spoolio stores only its digest
   and cannot show the plaintext again.
4. Store the key in protected device configuration, not in source control.

Every device request sends:

```http
Authorization: Bearer DEVICE_API_KEY
Accept: application/json
```

Use HTTPS whenever the request leaves the device itself. A `401` means the key
is absent, invalid, or was rotated. Do not put the key in a URL, log, NFC tag,
QR code, or crash report.

All routes below are relative to the Spoolio origin and begin with `/api`.

## Recommended measurement flow

1. `GET /api/hardware/heartbeat` when connecting and periodically while online.
2. Read a stable spool identifier. Despite the JSON name `nfc_tag_id`, Protocol
   v1 treats it as an opaque string: NFC, RFID, barcode, QR, or a locally entered
   identifier can all work if the same value is linked to the spool in Spoolio.
3. Optionally look it up with `GET /api/hardware/spool/{identifier}`.
4. Measure the **gross weight in grams**, including the empty spool.
5. Optionally post progress to `POST /api/hardware/event`.
6. Commit the measurement with `POST /api/hardware/weight-update`.

Spoolio subtracts the spool type's configured tare. Do not subtract tare in the
device. The accepted gross range is 0–10,000 g. A small apparent increase is
treated as measurement tolerance; a significant increase can be recorded as a
refill instead of negative consumption.

## Device endpoints

### Heartbeat

```http
GET /api/hardware/heartbeat
```

The response includes server time, device metadata, optional Wi-Fi/firmware
metadata, and the discoverable protocol contract:

```json
{
  "status": "ok",
  "protocol": {
    "name": "spoolio-hardware",
    "version": "1",
    "weight_unit": "g",
    "weight_type": "gross",
    "max_gross_weight": 10000.0
  }
}
```

### Spool lookup

```http
GET /api/hardware/spool/{url-encoded-identifier}
```

Returns the owner-scoped spool record, or `404` when the identifier is not
linked. Limit: 60 requests per minute.

### Weight update

```http
POST /api/hardware/weight-update
Content-Type: application/json

{"nfc_tag_id":"04A1B2C3D4","weight":912.4}
```

`weight` is gross grams. A successful response includes the updated spool,
calculated net weight, tare applied, consumption, and increase/refill flags.
If the identifier is unknown, Spoolio returns `404` with
`orphan_recorded: true` when it saved the reading for later linking. Treat that
as an accepted measurement, not a rapid-retry condition. Limit: 30 requests per
minute.

### Progress events (optional)

```http
POST /api/hardware/event
Content-Type: application/json

{
  "event_type": "stable_weight",
  "nfc_tag_id": "04A1B2C3D4",
  "weight": 912.4,
  "message": "optional diagnostic without secrets"
}
```

Recognized UI states include `scan_start`, `weighing`, `stable_weight`, `error`,
`ready`, `ready_to_weigh`, `waiting_clear`, and `waiting_removal`. Custom event
names are stored but may not receive special UI treatment. Event posting does
not update inventory; the weight-update endpoint is still required.

## Failure and retry rules

- `400`: fix the request; retrying it unchanged will not help.
- `401`: stop measurements that would be lost, surface a re-provisioning error,
  and wait for a valid device key.
- `404` from weight update with `orphan_recorded: true`: do not retry rapidly;
  the owner can link the identifier in Spoolio.
- `409`: the identifier or device conflicts with an existing record; require
  owner intervention.
- `429`: honor `Retry-After` and back off.
- `5xx` or network failure: retain the newest stable reading locally and retry
  with bounded exponential backoff and jitter.

Devices should debounce scans and upload only stable readings. Protocol v1 does
not define exactly-once request identifiers, so repeatedly replaying an old
measurement can distort event/history records even when the current weight is
unchanged.

## Board-neutral simulator

The standard-library client in `hardware/generic_client.py` exercises the same
contract without Arduino dependencies:

```bash
export SPOOLIO_URL=http://localhost:8000
export SPOOLIO_DEVICE_API_KEY='paste-the-one-time-device-key'

python hardware/generic_client.py heartbeat
python hardware/generic_client.py lookup '04A1B2C3D4'
python hardware/generic_client.py event stable_weight --identifier '04A1B2C3D4' --weight 912.4
python hardware/generic_client.py weight '04A1B2C3D4' 912.4
```

For a non-local server, use HTTPS. The client rejects cleartext HTTP to remote
hosts unless the explicit lab-only `--allow-http` flag is supplied.

#!/usr/bin/env python3
"""Board-neutral Spoolio hardware protocol client and command-line simulator."""

import argparse
import json
import math
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


# Kept here as well as in the server contract so this file remains directly
# runnable and easy to port without importing the Spoolio application.
MAX_GROSS_WEIGHT_GRAMS = 10_000.0


class HardwareAPIError(RuntimeError):
    """An HTTP or transport failure returned by the Spoolio service."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class SpoolioHardwareClient:
    """Minimal Protocol v1 client suitable for ports to other platforms."""

    def __init__(
        self,
        base_url,
        api_key,
        *,
        timeout=10.0,
        allow_insecure_http=False,
        opener=urlopen,
    ):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not include a query or fragment")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain credentials")
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme != "https"
            and parsed.hostname not in local_hosts
            and not allow_insecure_http
        ):
            raise ValueError(
                "HTTP exposes the device key; use HTTPS or pass allow_insecure_http"
            )
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key is required")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = float(timeout)
        self._opener = opener

    def _request(self, method, path, payload=None):
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "spoolio-generic-client/1",
        }
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{self.base_url}/api{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                detail = parsed.get("error") or parsed.get("msg") or detail
            except (json.JSONDecodeError, AttributeError):
                pass
            raise HardwareAPIError(str(detail).strip(), status=exc.code) from exc
        except URLError as exc:
            raise HardwareAPIError(f"Unable to reach Spoolio: {exc.reason}") from exc

        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise HardwareAPIError("Spoolio returned invalid JSON") from exc

    def heartbeat(self):
        return self._request("GET", "/hardware/heartbeat")

    def lookup(self, identifier):
        value = str(identifier).strip()
        if not value:
            raise ValueError("identifier is required")
        return self._request("GET", f"/hardware/spool/{quote(value, safe='')}")

    def update_weight(self, identifier, gross_weight):
        value = str(identifier).strip()
        if not value:
            raise ValueError("identifier is required")
        gross_weight = float(gross_weight)
        if not math.isfinite(gross_weight):
            raise ValueError("gross_weight must be finite")
        if gross_weight < 0 or gross_weight > MAX_GROSS_WEIGHT_GRAMS:
            raise ValueError(
                f"gross_weight must be between 0 and {MAX_GROSS_WEIGHT_GRAMS:g} g"
            )
        return self._request(
            "POST",
            "/hardware/weight-update",
            {"nfc_tag_id": value, "weight": gross_weight},
        )

    def event(self, event_type, *, identifier=None, weight=None, message=None):
        event_type = str(event_type).strip()
        if not event_type:
            raise ValueError("event_type is required")
        payload = {"event_type": event_type}
        if identifier is not None:
            payload["nfc_tag_id"] = str(identifier)
        if weight is not None:
            weight = float(weight)
            if not math.isfinite(weight):
                raise ValueError("event weight must be finite")
            payload["weight"] = weight
        if message is not None:
            payload["message"] = str(message)
        return self._request("POST", "/hardware/event", payload)


def _parser():
    parser = argparse.ArgumentParser(
        description="Exercise Spoolio Hardware Protocol v1 without a specific board",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("SPOOLIO_URL", "http://localhost:8000"),
        help="Spoolio origin (default: SPOOLIO_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("SPOOLIO_DEVICE_API_KEY"),
        help="device key (prefer SPOOLIO_DEVICE_API_KEY to shell history)",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="allow cleartext HTTP to a non-local host (unsafe outside a lab)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("heartbeat")

    lookup = commands.add_parser("lookup")
    lookup.add_argument("identifier")

    weight = commands.add_parser("weight")
    weight.add_argument("identifier")
    weight.add_argument("grams", type=float)

    event = commands.add_parser("event")
    event.add_argument("event_type")
    event.add_argument("--identifier")
    event.add_argument("--weight", type=float)
    event.add_argument("--message")
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.api_key:
        parser.error("provide --api-key or SPOOLIO_DEVICE_API_KEY")

    try:
        client = SpoolioHardwareClient(
            args.url,
            args.api_key,
            allow_insecure_http=args.allow_http,
        )
        if args.command == "heartbeat":
            result = client.heartbeat()
        elif args.command == "lookup":
            result = client.lookup(args.identifier)
        elif args.command == "weight":
            result = client.update_weight(args.identifier, args.grams)
        else:
            result = client.event(
                args.event_type,
                identifier=args.identifier,
                weight=args.weight,
                message=args.message,
            )
    except (HardwareAPIError, ValueError) as exc:
        prefix = f"HTTP {exc.status}: " if getattr(exc, "status", None) else ""
        print(f"{prefix}{exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""ShipmentTrack adapter for the reusable signed authorization module."""
from pathlib import Path

from authorization import AuthConfig, SignedLicenseVerifier, get_machine_id
from units import get_data_path


# All desktop programs can reuse this URL and public key. Keep the matching
# private key only in the administrator directory; never ship or commit it.
LICENSE_URL = (
    "https://raw.githubusercontent.com/Garlicgoose/"
    "MyWorkTool_License/main/ShipmentTrack_license.json"
)
PUBLIC_KEY_B64 = "F7jrPPnCNArA2bVatJ0NM6mMS1pazdkKgQCf/6h2QR0="
DATA_DIR = get_data_path()
CACHE_FILE = Path(DATA_DIR) / "authorization.cache"
NEUTRAL_ERROR = "A required service is unavailable. Please try again later."


def _make_verifier(url: str = LICENSE_URL) -> SignedLicenseVerifier:
    return SignedLicenseVerifier(AuthConfig(
        manifest_url=url,
        public_key_b64=PUBLIC_KEY_B64,
        cache_file=CACHE_FILE,
        app_id="shipment-track",
        offline_grace_seconds=24 * 60 * 60,
        generic_error=NEUTRAL_ERROR,
    ))


_verifier = _make_verifier()


def get_current_machine_id() -> str:
    return get_machine_id(DATA_DIR)


def verify(machine_code: str, url=None):
    """Return the legacy-compatible ``(ok, mode, error)`` tuple."""
    verifier = _verifier if url is None else _make_verifier(url)
    result = verifier.verify(machine_code)
    return result.ok, result.mode, result.error


def revalidate_session(machine_code: str):
    """Repeat signature and machine checks at a second execution point."""
    result = _verifier.revalidate_session(machine_code)
    return result.ok, result.mode, result.error

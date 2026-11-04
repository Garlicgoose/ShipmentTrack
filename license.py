# -*- coding: utf-8 -*-
"""ShipmentTrack adapter for the reusable signed runtime policy module."""
import json
from pathlib import Path

from authorization import (
    AuthConfig,
    SignedLicenseVerifier,
    VerificationResult,
    get_machine_id,
    payload_allows_machine,
    verify_signed_manifest,
)
from authorization.verifier import ManifestError
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
REVISION_FILE = Path(DATA_DIR) / "authorization.revision"
ONLINE_RECHECK_SECONDS = 24 * 60 * 60
OFFLINE_GRACE_SECONDS = 7 * 24 * 60 * 60
NEUTRAL_ERROR = "当前无法启动应用，请稍后重试。"


class ShipmentTrackVerifier(SignedLicenseVerifier):
    """Adds daily cache reuse and signed-manifest rollback protection."""

    def __init__(self, config, *, revision_file=REVISION_FILE, **kwargs):
        super().__init__(config, **kwargs)
        self.revision_file = Path(revision_file)

    def _read_cache_record(self):
        try:
            return json.loads(
                self._unprotector(self.config.cache_file.read_bytes()).decode("utf-8")
            )
        except Exception:
            return None

    def _read_highest_revision(self):
        try:
            record = json.loads(
                self._unprotector(self.revision_file.read_bytes()).decode("utf-8")
            )
            value = int(record["revision"])
            return value if value >= 1 else 0
        except Exception:
            return 0

    def _write_highest_revision(self, revision):
        try:
            protected = self._protector(json.dumps(
                {"revision": int(revision)},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"))
            self.revision_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.revision_file.with_suffix(self.revision_file.suffix + ".tmp")
            temporary.write_bytes(protected)
            temporary.replace(self.revision_file)
        except OSError as exc:
            raise ManifestError("unable to persist manifest revision") from exc

    def _authorize_document(self, document, machine_code):
        payload = verify_signed_manifest(document, self.config.public_key_b64)
        revision = int(payload["revision"])
        highest = self._read_highest_revision()
        if highest and revision < highest:
            raise ManifestError("signed manifest revision rollback")
        if revision > highest:
            self._write_highest_revision(revision)
        return payload_allows_machine(payload, machine_code)

    def verify_if_due(self, machine_code):
        """Use a valid recent cache; perform an online check at least daily."""
        record = self._read_cache_record()
        if record is not None:
            try:
                age = self._clock() - float(record["checked_at"])
            except (KeyError, TypeError, ValueError):
                age = ONLINE_RECHECK_SECONDS
            if -300 <= age < ONLINE_RECHECK_SECONDS:
                document = self._read_valid_cache(machine_code)
                if document is not None:
                    self._session_document = document
                    return VerificationResult(True, "recent-cache")
        return super().verify(machine_code)


def _make_verifier(url: str = LICENSE_URL) -> SignedLicenseVerifier:
    return ShipmentTrackVerifier(AuthConfig(
        manifest_url=url,
        public_key_b64=PUBLIC_KEY_B64,
        cache_file=CACHE_FILE,
        app_id="shipment-track",
        offline_grace_seconds=OFFLINE_GRACE_SECONDS,
        generic_error=NEUTRAL_ERROR,
    ))


_verifier = _make_verifier()


def get_current_machine_id() -> str:
    return get_machine_id(DATA_DIR)


def verify(machine_code: str, url=None):
    """Return the legacy-compatible ``(ok, mode, error)`` tuple."""
    verifier = _verifier if url is None else _make_verifier(url)
    result = verifier.verify_if_due(machine_code)
    return result.ok, result.mode, result.error


def revalidate_session(machine_code: str):
    """Repeat signature and machine checks at a second execution point."""
    result = _verifier.revalidate_session(machine_code)
    return result.ok, result.mode, result.error

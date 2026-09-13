# -*- coding: utf-8 -*-
"""Portable signed-license verification for Windows desktop applications.

The client contains only an Ed25519 public key.  A separately kept admin
private key signs the GitHub manifest.  Online denial always wins; a cached
success is used only when the network is unavailable and for at most one day.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import threading
import time
from typing import Callable, Optional
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


GENERIC_STARTUP_ERROR = "A required service is unavailable. Please try again later."
SCHEMA_VERSION = 1


class ManifestError(ValueError):
    """The remote document is malformed, unsigned, or unauthorized."""


@dataclass(frozen=True)
class AuthConfig:
    manifest_url: str
    public_key_b64: str
    cache_file: Path
    app_id: str = "desktop-app"
    offline_grace_seconds: int = 24 * 60 * 60
    timeout_seconds: float = 6.0
    generic_error: str = GENERIC_STARTUP_ERROR


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    mode: str
    error: Optional[str] = None


def machine_digest(machine_code: str) -> str:
    normalized = str(machine_code or "").strip().casefold().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def canonical_payload(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_signed_manifest(raw_document: bytes, public_key_b64: str) -> dict:
    try:
        document = json.loads(raw_document.decode("utf-8"))
        payload = document["payload"]
        signature = base64.b64decode(document["signature"], validate=True)
        public_key = base64.b64decode(public_key_b64, validate=True)
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            canonical_payload(payload),
        )
    except (KeyError, TypeError, ValueError, InvalidSignature, UnicodeError) as exc:
        raise ManifestError("invalid signed document") from exc

    machines = payload.get("machines")
    if (
        payload.get("schema") != SCHEMA_VERSION
        or not isinstance(payload.get("revision"), int)
        or payload["revision"] < 1
        or not isinstance(payload.get("issued_at"), str)
        or not isinstance(payload.get("global_enabled"), bool)
        or not isinstance(machines, dict)
    ):
        raise ManifestError("invalid payload schema")
    return payload


def payload_allows_machine(payload: dict, machine_code: str) -> bool:
    if payload.get("global_enabled") is not True:
        return False
    expected = machine_digest(machine_code)
    for stored_digest, enabled in payload.get("machines", {}).items():
        if isinstance(stored_digest, str) and hmac.compare_digest(stored_digest, expected):
            return enabled is True
    return False


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Protect cache data with the current Windows user's DPAPI key."""
    if not hasattr(ctypes, "windll"):
        raise OSError("Windows DPAPI is unavailable")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect:
        ok = function(
            ctypes.byref(source), None, None, None, None, 0x01, ctypes.byref(output)
        )
    else:
        description = wintypes.LPWSTR()
        ok = function(
            ctypes.byref(source), ctypes.byref(description), None, None, None, 0x01,
            ctypes.byref(output),
        )
    del source_buffer
    if not ok:
        raise OSError("DPAPI operation failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def protect_cache(data: bytes) -> bytes:
    return _dpapi(data, True)


def unprotect_cache(data: bytes) -> bytes:
    return _dpapi(data, False)


def fetch_manifest(url: str, timeout: float, app_id: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"SharedDesktopAuth/{app_id}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class SignedLicenseVerifier:
    def __init__(
        self,
        config: AuthConfig,
        *,
        fetcher: Callable[[str, float, str], bytes] = fetch_manifest,
        clock: Callable[[], float] = time.time,
        protector: Callable[[bytes], bytes] = protect_cache,
        unprotector: Callable[[bytes], bytes] = unprotect_cache,
    ):
        self.config = config
        self._fetcher = fetcher
        self._clock = clock
        self._protector = protector
        self._unprotector = unprotector
        self._session_document: Optional[bytes] = None
        self._lock = threading.Lock()

    def _denied(self, mode: str) -> VerificationResult:
        return VerificationResult(False, mode, self.config.generic_error)

    def _clear_cache(self) -> None:
        try:
            self.config.cache_file.unlink()
        except OSError:
            pass

    def _authorize_document(self, document: bytes, machine_code: str) -> bool:
        payload = verify_signed_manifest(document, self.config.public_key_b64)
        return payload_allows_machine(payload, machine_code)

    def _write_cache(self, document: bytes, machine_code: str) -> None:
        record = canonical_payload({
            "checked_at": self._clock(),
            "machine": machine_digest(machine_code),
            "manifest": base64.b64encode(document).decode("ascii"),
        })
        protected = self._protector(record)
        path = self.config.cache_file
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(protected)
        temporary.replace(path)

    def _read_valid_cache(self, machine_code: str) -> Optional[bytes]:
        try:
            record = json.loads(
                self._unprotector(self.config.cache_file.read_bytes()).decode("utf-8")
            )
            checked_at = float(record["checked_at"])
            now = self._clock()
            age = now - checked_at
            if age < -300 or age > self.config.offline_grace_seconds:
                return None
            if not hmac.compare_digest(record["machine"], machine_digest(machine_code)):
                return None
            document = base64.b64decode(record["manifest"], validate=True)
            if not self._authorize_document(document, machine_code):
                return None
            return document
        except Exception:
            return None

    def verify(self, machine_code: str) -> VerificationResult:
        """Verify online first; use the one-day cache only for connection failures."""
        with self._lock:
            try:
                document = self._fetcher(
                    self.config.manifest_url,
                    self.config.timeout_seconds,
                    self.config.app_id,
                )
            except urllib.error.HTTPError:
                self._clear_cache()
                return self._denied("remote-error")
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                document = self._read_valid_cache(machine_code)
                if document is None:
                    return self._denied("unavailable")
                self._session_document = document
                return VerificationResult(True, "offline-cache")

            try:
                allowed = self._authorize_document(document, machine_code)
            except ManifestError:
                self._clear_cache()
                return self._denied("invalid-response")
            if not allowed:
                self._clear_cache()
                return self._denied("unavailable")
            try:
                self._write_cache(document, machine_code)
            except OSError:
                pass
            self._session_document = document
            return VerificationResult(True, "online")

    def revalidate_session(self, machine_code: str) -> VerificationResult:
        """Second verification point without another network request."""
        with self._lock:
            if self._session_document is None:
                return self._denied("session-missing")
            try:
                allowed = self._authorize_document(self._session_document, machine_code)
            except ManifestError:
                allowed = False
            return (
                VerificationResult(True, "session")
                if allowed
                else self._denied("session-invalid")
            )

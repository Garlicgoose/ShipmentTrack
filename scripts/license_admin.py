# -*- coding: utf-8 -*-
"""Administrator CLI for the shared Ed25519 authorization manifest."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from portable_auth import canonical_payload, machine_digest


def generate_keys(private_path: Path, public_path: Path) -> str:
    private_path = Path(private_path)
    public_path = Path(public_path)
    if private_path.exists() or public_path.exists():
        raise FileExistsError("Refusing to overwrite an existing key")
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(base64.b64encode(private_raw).decode("ascii"), "ascii")
    public_b64 = base64.b64encode(public_raw).decode("ascii")
    public_path.write_text(public_b64, "ascii")
    return public_b64


def _normalized_machines(source) -> dict[str, bool]:
    if not isinstance(source, dict):
        raise ValueError("Machine list must be a JSON object")
    normalized = {}
    for identifier, enabled in source.items():
        key = str(identifier).strip().casefold()
        digest = key if re.fullmatch(r"[0-9a-f]{64}", key) else machine_digest(key)
        normalized[digest] = enabled is True
    return dict(sorted(normalized.items()))


def build_signed_manifest(
    private_key_b64: str,
    machines: dict,
    *,
    revision: int,
    global_enabled: bool = True,
    issued_at: str | None = None,
) -> dict:
    if revision < 1:
        raise ValueError("Revision must be at least 1")
    private_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(private_key_b64.strip(), validate=True)
    )
    payload = {
        "schema": 1,
        "revision": revision,
        "issued_at": issued_at or datetime.now(timezone.utc).isoformat(),
        "global_enabled": bool(global_enabled),
        "machines": _normalized_machines(machines),
    }
    signature = private_key.sign(canonical_payload(payload))
    return {
        "payload": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def sign_file(
    private_path: Path,
    machines_path: Path,
    output_path: Path,
    *,
    revision: int,
    global_enabled: bool = True,
) -> dict:
    private_b64 = Path(private_path).read_text("ascii").strip()
    machines = json.loads(Path(machines_path).read_text("utf-8-sig"))
    document = build_signed_manifest(
        private_b64,
        machines,
        revision=revision,
        global_enabled=global_enabled,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        "utf-8",
    )
    return document


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a signed authorization manifest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate-keys", help="create one Ed25519 key pair")
    generate.add_argument("--private", required=True, type=Path)
    generate.add_argument("--public", required=True, type=Path)

    sign = subparsers.add_parser("sign", help="sign a machine switch JSON file")
    sign.add_argument("--private", required=True, type=Path)
    sign.add_argument("--machines", required=True, type=Path)
    sign.add_argument("--output", required=True, type=Path)
    sign.add_argument("--revision", required=True, type=int)
    sign.add_argument("--disable-global", action="store_true")

    digest = subparsers.add_parser("hash", help="hash one machine code")
    digest.add_argument("machine_code")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate-keys":
        print(generate_keys(args.private, args.public))
    elif args.command == "sign":
        sign_file(
            args.private,
            args.machines,
            args.output,
            revision=args.revision,
            global_enabled=not args.disable_global,
        )
        print(args.output)
    else:
        print(machine_digest(args.machine_code))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

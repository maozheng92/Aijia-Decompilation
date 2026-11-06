#!/usr/bin/env python3
"""Try to unlock PKCS#12 files inside the 爱家 APK.

Does not print or commit private key material. Writes PEM files next to
the integration if a known password opens the store.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

KNOWN_PASSWORDS = [
    "186e990688070325a1c4b0ce275d2388",
    "multiscreen123",
    "ayd6afbj2huf3",
]


def try_export(p12: Path, password: str, dest_dir: Path) -> bool:
    cert = dest_dir / "client.pem"
    key = dest_dir / "client.key"
    for extra in ([], ["-legacy"]):
        cert_cmd = [
            "openssl",
            "pkcs12",
            "-in",
            str(p12),
            "-passin",
            f"pass:{password}",
            "-clcerts",
            "-nokeys",
            "-out",
            str(cert),
            *extra,
        ]
        key_cmd = [
            "openssl",
            "pkcs12",
            "-in",
            str(p12),
            "-passin",
            f"pass:{password}",
            "-nocerts",
            "-nodes",
            "-out",
            str(key),
            *extra,
        ]
        cert_ok = subprocess.run(cert_cmd, capture_output=True).returncode == 0
        key_ok = subprocess.run(key_cmd, capture_output=True).returncode == 0
        if cert_ok and key_ok and cert.stat().st_size > 0 and key.stat().st_size > 0:
            key.chmod(0o600)
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apk",
        default="com.hisense.ms.fly2tv.apk",
        type=Path,
        help="Path to the 爱家 APK",
    )
    parser.add_argument(
        "--out",
        default=Path("custom_components/hisense_e7n/certs"),
        type=Path,
    )
    args = parser.parse_args()
    if not args.apk.exists():
        print(f"APK not found: {args.apk}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(args.apk) as zf:
            p12_names = [name for name in zf.namelist() if name.lower().endswith(".p12")]
            if not p12_names:
                print("No .p12 inside APK", file=sys.stderr)
                return 2
            for name in p12_names:
                target = tmp_path / Path(name).name
                target.write_bytes(zf.read(name))
                for password in KNOWN_PASSWORDS:
                    if try_export(target, password, args.out):
                        print(f"Wrote {args.out / 'client.pem'} from {name}")
                        return 0
    print(
        "Could not unlock any PKCS#12 with known passwords. "
        "Place client.pem / client.key yourself if MQTT rc=5.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

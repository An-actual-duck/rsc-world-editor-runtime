#!/usr/bin/env python3
"""Pinned build inputs for Base's existing desktop presenter (not gameplay).

Hashes verified against repo.maven.apache.org on 2026-09-11. Provisioning is
explicit; normal Base builds are offline and refuse missing or changed inputs.
"""

import argparse
import hashlib
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "PC_Client/lib/lwjgl"
PAYLOAD_PREFIXES = ("org/lwjgl/", "linux/x64/org/lwjgl/", "windows/x64/org/lwjgl/")
PINS = {
    "lwjgl-3.3.4.jar": "6844ff591a4fa4175136416eb1d93ede336224fe3e2026ff29993a93a000b169",
    "lwjgl-3.3.4-natives-linux.jar": "8bb4acce4516fe66a70603258651eba56841e65f2cabd07ca8eb8fb5e30ee7f9",
    "lwjgl-3.3.4-natives-windows.jar": "b99d07307ccab60ba1ec5572d1cce7a6936c5fd664cc70eb54091602c322470d",
    "lwjgl-glfw-3.3.4.jar": "00bef976dc83dd4fdb2cb8dce4e37c7912671698e4c9765511fcbe3a823071af",
    "lwjgl-glfw-3.3.4-natives-linux.jar": "102b98a719c826ac9cf178e3d7af2cdecbf8a01cdf168d3481a0e31c427c430a",
    "lwjgl-glfw-3.3.4-natives-windows.jar": "85348d9687b12837f9dea77de2bc854d3d93c31fcb6d30a84dc54cc9ceac9c5d",
    "lwjgl-opengl-3.3.4.jar": "ed0f3d6a2aa564c672c59b9a51343ff2cb657bf6f5e3c8b8b96c04b42616d529",
    "lwjgl-opengl-3.3.4-natives-linux.jar": "ad4582790a5f8c1dce8fac43df68e8e05f5fe13cb88432bdbd69658cb36bce87",
    "lwjgl-opengl-3.3.4-natives-windows.jar": "1cf72c57cdf66b810562555fa8704f027ed516346b6807b8909b5465e81702ec",
}


def check_file(path, expected):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing/unsafe pinned LWJGL input: {path}; run scripts/current-base-lwjgl.py --download")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Changed pinned LWJGL input: {path}")


def validate(lib=LIB):
    if lib.is_symlink():
        raise ValueError("LWJGL dependency directory must not be a symlink")
    for name, digest in PINS.items():
        check_file(lib / name, digest)
    extras = {str(path.relative_to(lib)) for path in lib.rglob("*.jar")} - set(PINS)
    if extras:
        raise ValueError(f"Unexpected LWJGL dependency inventory: {sorted(extras)}")


def payload(lib=LIB):
    validate(lib)
    result = {}
    for name in sorted(PINS):
        with zipfile.ZipFile(lib / name) as archive:
            for entry in archive.namelist():
                # Metadata and module-info are intentionally shared in fat jars.
                if entry.endswith("/") or not entry.startswith(PAYLOAD_PREFIXES):
                    continue
                data = archive.read(entry)
                if entry in result and result[entry] != data:
                    raise ValueError(f"Conflicting pinned LWJGL payload: {entry}")
                result[entry] = data
    return result


def verify_archive(path, lib=LIB):
    expected = payload(lib)
    with zipfile.ZipFile(path) as archive:
        actual = {entry for entry in archive.namelist()
                  if not entry.endswith("/") and entry.startswith(PAYLOAD_PREFIXES)}
        if actual != set(expected):
            raise ValueError("Base client LWJGL class/native inventory differs from pinned presenter inputs")
        for entry, data in expected.items():
            if archive.read(entry) != data:
                raise ValueError(f"Base client contains changed LWJGL payload: {entry}")


def provision(lib, source=None):
    if source is not None:
        validate(source)
    if lib.is_symlink():
        raise ValueError("LWJGL dependency directory must not be a symlink")
    lib.mkdir(parents=True, exist_ok=True)
    for name, digest in PINS.items():
        destination = lib / name
        if destination.exists() or destination.is_symlink():
            check_file(destination, digest)
            continue
        if source is not None:
            data = (source / name).read_bytes()
        else:
            module = name.split("-3.3.4", 1)[0]
            url = f"https://repo.maven.apache.org/maven2/org/lwjgl/{module}/3.3.4/{name}"
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Downloaded/staged LWJGL input hash mismatch: {name}")
        # Never overwrite even if another process created the destination.
        with destination.open("xb") as stream:
            stream.write(data)
    validate(lib)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lib", type=Path, default=LIB)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--download", action="store_true")
    mode.add_argument("--stage-from", type=Path)
    parser.add_argument("--archive", type=Path)
    options = parser.parse_args()
    try:
        if options.download or options.stage_from:
            provision(options.lib, options.stage_from)
        validate(options.lib)
        if options.archive:
            verify_archive(options.archive, options.lib)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"Current Base LWJGL verification failed: {error}", file=sys.stderr)
        return 2
    print("Verified pinned LWJGL 3.3.4 presenter inputs (Linux/Windows x64)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build and verify the provider-owned Current Base candidate artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "current-platform"
DEFAULT_OUTPUT = ROOT / "output/current-platform/current-base-v1"
COMPOSITION_TOOL = ROOT / "scripts/current-platform-composition.py"
VERIFY_TOOL = ROOT / "scripts/verify-current-base.py"
FIXED_ZIP_TIME = (2000, 1, 1, 0, 0, 0)


def load_composition_tool():
    spec = importlib.util.spec_from_file_location(
        "current_platform_composition", COMPOSITION_TOOL
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load current platform composition tool")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def normalize_zip(path: Path) -> None:
    """Rewrite a ZIP/JAR with stable order, metadata, and duplicate rejection."""
    temporary = path.with_suffix(path.suffix + ".normalized")
    with zipfile.ZipFile(path) as source:
        records = []
        names: set[str] = set()
        folded: set[str] = set()
        for info in source.infolist():
            if info.is_dir():
                continue
            if info.filename in names:
                raise RuntimeError(f"duplicate archive entry in {path}: {info.filename}")
            casefolded = info.filename.casefold()
            if casefolded in folded:
                raise RuntimeError(
                    f"case-fold archive collision in {path}: {info.filename}"
                )
            names.add(info.filename)
            folded.add(casefolded)
            records.append((info.filename, source.read(info)))
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as target:
        for name, payload in sorted(records):
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 << 16)
            target.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    os.replace(temporary, path)


def tool_version(command: list[str]) -> str:
    completed = subprocess.run(
        command, cwd=ROOT, check=True, text=True, capture_output=True
    )
    return (completed.stdout or completed.stderr).splitlines()[0]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(output: Path) -> Path:
    composition = load_composition_tool()
    catalog = composition.Catalog(CATALOG_ROOT)
    composition.validate_catalog(catalog)
    variant_path, variant = catalog.variants["current-base-v1"]

    if output.exists():
        shutil.rmtree(output)
    server_output = output / "server"
    client_output = output / "client"
    runtime_output = output / "runtime"
    server_output.mkdir(parents=True)
    client_output.mkdir(parents=True)
    runtime_output.mkdir(parents=True)

    pairing = {
        "artifactContract": "current-platform-runtime-artifact-v1",
        "handshakeId": catalog.platform["protocol"]["handshakeId"],
        "moduleSetHash": composition.canonical_hash([]),
        "platformManifestHash": composition.canonical_hash(
            composition.load_json(catalog.platform_path)
        ),
        "platformReleaseId": catalog.platform["platformReleaseId"],
        "variantId": variant["variantId"],
        "variantManifestHash": composition.canonical_hash(
            composition.load_json(variant_path)
        ),
    }
    marker = output / "build/rsc-current-composition.properties"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        "".join(f"{key}={pairing[key]}\n" for key in sorted(pairing)),
        encoding="ascii",
    )

    run([sys.executable, "tools/generators/run-generators.py", "--check"])
    ant = ROOT / "tools/vendor/apache-ant-1.10.5/bin/ant"
    ant_prefix = ["sh", os.fspath(ant)]
    run(
        ant_prefix
        + [
            f"-Djar={server_output / 'core.jar'}",
            f"-Dcomposition.identity.file={marker}",
            "compile_core",
        ],
        ROOT / "server",
    )
    run(
        ant_prefix
        + [
            f"-Djar={server_output / 'core.jar'}",
            f"-Dplugin.jar={server_output / 'plugins.jar'}",
            "-Dplugin.includes=com/openrsc/server/plugins/authentic/**/*.java,com/openrsc/server/plugins/shared/**/*.java",
            "compile_plugins",
        ],
        ROOT / "server",
    )
    run(
        ant_prefix
        + [
            f"-Djar={client_output / 'Open_RSC_Client.jar'}",
            f"-Dcomposition.identity.file={marker}",
            "-Dcurrent.asset.includes=ui/world-editor/**",
            "compile",
        ],
        ROOT / "Client_Base",
    )
    for archive in (
        server_output / "core.jar",
        server_output / "plugins.jar",
        client_output / "Open_RSC_Client.jar",
    ):
        normalize_zip(archive)

    shutil.copy2(CATALOG_ROOT / "runtime/current-base-v1/profile.json", runtime_output)
    shutil.copy2(marker, runtime_output / "pairing.properties")
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout.strip()
    write_json(
        runtime_output / "build-provenance.json",
        {
            "schemaId": "current-base-build-provenance-v1",
            "manifestType": "current-base-build-provenance",
            "sourceAuthority": "selected-current-composition-source",
            "sourceCommit": source_commit,
            "receiptAuthority": "never",
            "archiveNormalization": "sorted-path-fixed-2000-01-01-deflate9-v1",
            "java": tool_version(["java", "-version"]),
            "ant": tool_version(["sh", os.fspath(ant), "-version"]),
            "pairing": pairing,
        },
    )
    shutil.rmtree(output / "build")

    identity = composition.resolve_composition(
        composition.Catalog(CATALOG_ROOT), "current-base-v1", [], ROOT
    )
    identity_path = output / "composition-identity.json"
    write_json(identity_path, identity)
    run(
        [
            sys.executable,
            os.fspath(VERIFY_TOOL),
            "--identity",
            os.fspath(identity_path),
            "--payload-root",
            os.fspath(ROOT),
        ]
    )
    return identity_path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args()


def main() -> int:
    parse_arguments()
    identity = build(DEFAULT_OUTPUT)
    print(f"Current Base candidate verified: {identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

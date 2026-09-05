#!/usr/bin/env python3
"""Build and verify the provider-owned Current Base candidate artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "current-platform"
DEFAULT_OUTPUT = ROOT / "output/current-platform/current-base-v1"
COMPOSITION_TOOL = ROOT / "scripts/current-platform-composition.py"
VERIFY_TOOL = ROOT / "scripts/verify-current-base.py"
FIXED_ZIP_TIME = (2000, 1, 1, 0, 0, 0)
CONTENT_MANIFEST = CATALOG_ROOT / "runtime/current-base-v1/server-content.json"
CONTENT_CONFIG_ROOT = CATALOG_ROOT / "runtime/current-base-v1/server"
CLIENT_CONTENT_MANIFEST = CATALOG_ROOT / "runtime/current-base-v1/client-content.json"


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


def filtered_xml(payload: bytes, transform: str, limits: dict[str, int]) -> bytes:
    root = ET.fromstring(payload)
    if transform == "vanilla-scenery-prefix-v1":
        children = list(root)
        expected = limits["sceneryMaxId"] + 1
        if len(children) < expected:
            raise RuntimeError("source scenery definitions do not cover vanilla IDs")
        for child in children[expected:]:
            root.remove(child)
    else:
        if transform == "vanilla-item-map-v1":
            key_limit = limits["itemMaxId"]
        elif transform == "vanilla-npc-map-v1":
            key_limit = limits["npcMaxId"]
        elif transform == "vanilla-scenery-map-v1":
            key_limit = limits["sceneryMaxId"]
        elif transform == "vanilla-item-array-v1":
            key_limit = None
        else:
            raise RuntimeError(f"unknown Current Base content transform: {transform}")
        for child in list(root):
            remove = False
            direct_key = child.find("int")
            if key_limit is not None and direct_key is not None:
                try:
                    remove = int(direct_key.text or "") > key_limit
                except ValueError as error:
                    raise RuntimeError("definition map has a malformed numeric key") from error
            for value in child.iter():
                tag = value.tag.lower()
                if not any(token in tag for token in ("itemid", "prodid", "runeid")):
                    continue
                try:
                    identifier = int(value.text or "")
                except ValueError as error:
                    raise RuntimeError("definition table has a malformed item ID") from error
                if identifier > limits["itemMaxId"]:
                    remove = True
            if remove:
                root.remove(child)
    return ET.tostring(root, encoding="utf-8", short_empty_elements=True) + b"\n"


def write_server_content_archive(path: Path) -> None:
    manifest = json.loads(CONTENT_MANIFEST.read_text(encoding="utf-8"))
    limits = manifest["definitionLimits"]
    records: dict[str, bytes] = {
        manifest["configurationEntry"]: (
            CONTENT_CONFIG_ROOT / manifest["configurationEntry"]
        ).read_bytes(),
        manifest["connectionsEntry"]: (
            CONTENT_CONFIG_ROOT / manifest["connectionsEntry"]
        ).read_bytes(),
    }
    for record in manifest["sourceFiles"]:
        source = ROOT / record["sourcePath"]
        payload = source.read_bytes()
        transform = record["transform"]
        if transform != "copy":
            payload = filtered_xml(payload, transform, limits)
        if record["bundlePath"] in records:
            raise RuntimeError("duplicate Current Base server content path")
        records[record["bundlePath"]] = payload
    for record in manifest["generatedFiles"]:
        if record["bundlePath"] in records:
            raise RuntimeError("duplicate Current Base generated content path")
        records[record["bundlePath"]] = record["content"].encode("utf-8")
    folded: set[str] = set()
    for name in records:
        if name.startswith("/") or "\\" in name or ".." in Path(name).parts:
            raise RuntimeError(f"unsafe Current Base server content path: {name}")
        if name.casefold() in folded:
            raise RuntimeError(f"case-fold Current Base content collision: {name}")
        folded.add(name.casefold())
        for forbidden in manifest["forbiddenPathFragments"]:
            if forbidden.casefold() in name.casefold():
                raise RuntimeError(f"Advanced-only path entered Current Base content: {name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, payload in sorted(records.items()):
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)


def write_client_content_archive(path: Path) -> None:
    manifest = json.loads(CLIENT_CONTENT_MANIFEST.read_text(encoding="utf-8"))
    records: dict[str, bytes] = {}
    for tree in manifest["sourceTrees"]:
        source_root = ROOT / tree["sourcePath"]
        if not source_root.is_dir() or source_root.is_symlink():
            raise RuntimeError("Current Base client content tree is missing or unsafe")
        for source in sorted(source_root.rglob("*")):
            if source.is_dir():
                continue
            if not source.is_file() or source.is_symlink():
                raise RuntimeError(f"unsafe Current Base client content file: {source}")
            relative = source.relative_to(source_root).as_posix()
            records[f'{tree["bundlePath"]}/{relative}'] = source.read_bytes()
    for record in manifest["sourceFiles"]:
        bundle_path = record["bundlePath"]
        if bundle_path in records:
            raise RuntimeError("duplicate Current Base client content path")
        records[bundle_path] = (ROOT / record["sourcePath"]).read_bytes()
    folded: set[str] = set()
    for name in records:
        if name.startswith("/") or "\\" in name or ".." in Path(name).parts:
            raise RuntimeError(f"unsafe Current Base client content path: {name}")
        if name.casefold() in folded:
            raise RuntimeError(f"case-fold Current Base client content collision: {name}")
        folded.add(name.casefold())
        if any(fragment.casefold() in name.casefold()
               for fragment in manifest["forbiddenPathFragments"]):
            raise RuntimeError(f"Advanced-only path entered client content: {name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, payload in sorted(records.items()):
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)


def source_tree_state(composition) -> tuple[str, bool, str]:
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True,
        capture_output=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, check=True, text=True, capture_output=True,
    ).stdout
    listed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.split(b"\0")
    records = []
    for encoded in sorted(path for path in listed if path):
        relative = encoded.decode("utf-8")
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"candidate source must be a regular file: {relative}")
        records.append(
            {
                "path": relative,
                "mode": format(path.stat().st_mode & 0o777, "04o"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return source_commit, bool(status), composition.canonical_hash(records)


def build(output: Path, allow_dirty: bool) -> Path:
    composition = load_composition_tool()
    catalog = composition.Catalog(CATALOG_ROOT)
    composition.validate_catalog(catalog)
    variant_path, variant = catalog.variants["current-base-v1"]
    source_commit, source_tree_dirty, source_tree_fingerprint = source_tree_state(
        composition
    )
    if source_tree_dirty and not allow_dirty:
        raise RuntimeError(
            "official Current Base candidate build requires a clean provider source tree"
        )

    if output.exists():
        shutil.rmtree(output)
    server_output = output / "server"
    client_output = output / "client"
    runtime_output = output / "runtime"
    tools_output = output / "tools"
    server_output.mkdir(parents=True)
    client_output.mkdir(parents=True)
    runtime_output.mkdir(parents=True)
    tools_output.mkdir(parents=True)

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
    run(ant_prefix + ["clean", "jar"], ROOT / "tools/layered-maps")
    shutil.copy2(
        ROOT / "tools/layered-maps/build/layered-maps.jar",
        tools_output / "layered-maps.jar",
    )
    for archive in (
        server_output / "core.jar",
        server_output / "plugins.jar",
        client_output / "Open_RSC_Client.jar",
        tools_output / "layered-maps.jar",
    ):
        normalize_zip(archive)

    write_server_content_archive(server_output / "content.zip")
    write_client_content_archive(client_output / "content.zip")

    shutil.copy2(CATALOG_ROOT / "runtime/current-base-v1/profile.json", runtime_output)
    shutil.copy2(marker, runtime_output / "pairing.properties")
    write_json(
        runtime_output / "build-provenance.json",
        {
            "schemaId": "current-base-build-provenance-v1",
            "manifestType": "current-base-build-provenance",
            "sourceAuthority": "selected-current-composition-source",
            "sourceCommit": source_commit,
            "sourceTreeDirty": source_tree_dirty,
            "sourceTreeFingerprint": source_tree_fingerprint,
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
    parser.add_argument(
        "--test-allow-dirty",
        action="store_true",
        help="Allow a dirty source tree while recording that fact; tests only.",
    )
    return parser.parse_args()


def main() -> int:
    options = parse_arguments()
    try:
        identity = build(DEFAULT_OUTPUT, options.test_allow_dirty)
    except RuntimeError as error:
        print(f"Current Base candidate build failed: {error}", file=sys.stderr)
        return 2
    print(f"Current Base candidate verified: {identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

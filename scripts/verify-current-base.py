#!/usr/bin/env python3
"""Source-tree verifier for a resolved Current Base artifact pair.

This is build/candidate evidence. It is not installed-runtime startup or login
enforcement and intentionally refuses to describe itself as such.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "scripts/current-platform-composition.py"
CATALOG_ROOT = ROOT / "current-platform"
PAIRING_ENTRY = "META-INF/rsc-current-composition.properties"
PAIRING_KEYS = {
    "artifactContract",
    "handshakeId",
    "moduleSetHash",
    "platformManifestHash",
    "platformReleaseId",
    "variantId",
    "variantManifestHash",
}


class VerificationError(ValueError):
    pass


def load_composition_tool():
    spec = importlib.util.spec_from_file_location("current_platform_composition", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise VerificationError("cannot load current platform composition tool")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive_names(path: Path) -> set[str]:
    names: set[str] = set()
    folded: set[str] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            for record in archive.infolist():
                if record.is_dir():
                    continue
                if record.filename in names:
                    raise VerificationError(
                        f"{path.name} contains duplicate entry {record.filename}"
                    )
                casefolded = record.filename.casefold()
                if casefolded in folded:
                    raise VerificationError(
                        f"{path.name} contains case-fold collision {record.filename}"
                    )
                names.add(record.filename)
                folded.add(casefolded)
    except (OSError, zipfile.BadZipFile) as error:
        raise VerificationError(f"cannot inspect {path}: {error}") from error
    return names


def parse_pairing(payload: bytes, label: str) -> dict[str, str]:
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise VerificationError(f"{label} pairing marker is not ASCII") from error
    if "\r" in text or not text.endswith("\n"):
        raise VerificationError(f"{label} pairing marker is not canonical")
    result: dict[str, str] = {}
    prior = ""
    for line in text.splitlines():
        if line.count("=") != 1:
            raise VerificationError(f"{label} pairing marker has malformed row")
        key, value = line.split("=", 1)
        if key <= prior or key in result or not value:
            raise VerificationError(f"{label} pairing marker has unordered/duplicate row")
        prior = key
        result[key] = value
    if set(result) != PAIRING_KEYS:
        raise VerificationError(f"{label} pairing marker keys differ from the contract")
    return result


def read_pairing(path: Path, label: str) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        try:
            return parse_pairing(archive.read(PAIRING_ENTRY), label)
        except KeyError as error:
            raise VerificationError(f"{label} lacks {PAIRING_ENTRY}") from error


def require_exact_keys(value: dict, keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise VerificationError(f"{label} keys differ from the closed contract")


def validate_profile(path: Path) -> dict:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read Current Base profile: {error}") from error
    require_exact_keys(
        profile,
        {
            "schemaId",
            "manifestType",
            "variantId",
            "installabilityBlockers",
            "pluginSourceSets",
            "clientAssetSets",
            "statePolicy",
            "requiredRuntimeClasses",
            "requiredPluginClasses",
            "advancedExclusions",
        },
        "profile",
    )
    if profile["schemaId"] != "current-base-runtime-profile-v1":
        raise VerificationError("Current Base profile has wrong schemaId")
    if profile["manifestType"] != "current-base-runtime-profile":
        raise VerificationError("Current Base profile has wrong manifestType")
    if profile["variantId"] != "current-base-v1":
        raise VerificationError("Current Base profile names another variant")
    if profile["installabilityBlockers"] != [
        "content-neutral-server-config-and-definitions-v1",
        "transactional-state-migration-row-v1",
        "base-gameplay-state-runtime-execution-v1",
        "runtime-enforced-server-client-startup-handshake-v1",
    ]:
        raise VerificationError("Current Base installability blockers are incomplete")
    if profile["pluginSourceSets"] != ["authentic", "shared"]:
        raise VerificationError("Current Base plugin source sets are not conservative")
    if profile["clientAssetSets"] != ["platform-world-editor-ui"]:
        raise VerificationError("Current Base client asset set is not conservative")
    if profile["statePolicy"] != {
        "contractId": "canonical-public-state-v1",
        "durableLocation": "outside-code-runtime",
        "migration": "transactional",
        "rollback": "exact-predecessor",
    }:
        raise VerificationError("Current Base public state policy is incomplete")
    exclusions = profile["advancedExclusions"]
    require_exact_keys(
        exclusions,
        {"pluginPrefixes", "clientResourcePrefixes", "configuration"},
        "advancedExclusions",
    )
    if not exclusions["configuration"] or any(
        value is not False for value in exclusions["configuration"].values()
    ):
        raise VerificationError("Current Base must explicitly disable Advanced configuration")
    return profile


def validate_build_provenance(path: Path, expected_pairing: dict[str, str]) -> None:
    try:
        provenance = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read build provenance: {error}") from error
    require_exact_keys(
        provenance,
        {
            "schemaId", "manifestType", "sourceAuthority", "sourceCommit",
            "sourceTreeDirty", "sourceTreeFingerprint",
            "receiptAuthority", "archiveNormalization", "java", "ant", "pairing",
        },
        "build provenance",
    )
    if provenance["schemaId"] != "current-base-build-provenance-v1":
        raise VerificationError("build provenance has wrong schemaId")
    if provenance["manifestType"] != "current-base-build-provenance":
        raise VerificationError("build provenance has wrong manifestType")
    if provenance["sourceAuthority"] != "selected-current-composition-source":
        raise VerificationError("build provenance is not source-authoritative")
    if provenance["receiptAuthority"] != "never":
        raise VerificationError("build provenance permits receipt authority")
    if provenance["archiveNormalization"] != "sorted-path-fixed-2000-01-01-deflate9-v1":
        raise VerificationError("build provenance has unknown archive normalization")
    source_commit = provenance["sourceCommit"]
    if not isinstance(source_commit, str) or len(source_commit) not in (40, 64):
        raise VerificationError("build provenance has malformed source commit")
    if not all(character in "0123456789abcdef" for character in source_commit):
        raise VerificationError("build provenance has malformed source commit")
    if not isinstance(provenance["sourceTreeDirty"], bool):
        raise VerificationError("build provenance lacks source tree dirty state")
    source_tree_fingerprint = provenance["sourceTreeFingerprint"]
    if not isinstance(source_tree_fingerprint, str) or len(source_tree_fingerprint) != 64:
        raise VerificationError("build provenance has malformed source tree fingerprint")
    if not all(character in "0123456789abcdef" for character in source_tree_fingerprint):
        raise VerificationError("build provenance has malformed source tree fingerprint")
    if not isinstance(provenance["java"], str) or not provenance["java"]:
        raise VerificationError("build provenance lacks Java toolchain identity")
    if not isinstance(provenance["ant"], str) or not provenance["ant"]:
        raise VerificationError("build provenance lacks Ant toolchain identity")
    if provenance["pairing"] != expected_pairing:
        raise VerificationError("build provenance pairing differs from composition")


def inventory_path(identity: dict, role: str, payload_root: Path) -> Path:
    records = [record for record in identity["bundleInventory"] if record["role"] == role]
    if len(records) != 1:
        raise VerificationError(f"Current Base requires exactly one {role} artifact")
    spec = json.loads(
        (CATALOG_ROOT / "bundle-specs/current-base-v1.json").read_text(encoding="utf-8")
    )
    matches = [artifact for artifact in spec["artifacts"] if artifact["role"] == role]
    if len(matches) != 1:
        raise VerificationError(f"bundle spec requires exactly one {role} source")
    return payload_root / matches[0]["sourcePath"]


def verify(identity_path: Path, payload_root: Path) -> dict:
    composition = load_composition_tool()
    catalog = composition.Catalog(CATALOG_ROOT)
    composition.validate_catalog(catalog)
    expected = composition.resolve_composition(catalog, "current-base-v1", [], payload_root)
    try:
        supplied = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read composition identity: {error}") from error
    if supplied != expected:
        raise VerificationError("composition identity differs from provider artifacts")
    if supplied["variantId"] != "current-base-v1" or supplied["installable"]:
        raise VerificationError("composition is not the bounded non-installable Base candidate")

    server = inventory_path(supplied, "server-runtime", payload_root)
    plugins = inventory_path(supplied, "server-plugins", payload_root)
    client = inventory_path(supplied, "client-runtime", payload_root)
    profile_path = inventory_path(supplied, "runtime-profile", payload_root)
    pairing_path = inventory_path(supplied, "server-client-pairing", payload_root)
    provenance_path = inventory_path(supplied, "build-provenance", payload_root)
    server_names = archive_names(server)
    plugin_names = archive_names(plugins)
    client_names = archive_names(client)
    profile = validate_profile(profile_path)

    for required in profile["requiredRuntimeClasses"]:
        if required not in server_names:
            raise VerificationError(f"server lacks canonical runtime class {required}")
    for required in profile["requiredPluginClasses"]:
        if required not in plugin_names:
            raise VerificationError(f"Base lacks declared public plugin {required}")
    for name in plugin_names:
        if name == "META-INF/MANIFEST.MF":
            continue
        if not name.startswith(
            ("com/openrsc/server/plugins/authentic/", "com/openrsc/server/plugins/shared/")
        ):
            raise VerificationError(f"Base plugin archive has unowned entry {name}")
    for prefix in profile["advancedExclusions"]["pluginPrefixes"]:
        if any(name.startswith(prefix) for name in plugin_names):
            raise VerificationError(f"Base contains Advanced plugin prefix {prefix}")
    for prefix in profile["advancedExclusions"]["clientResourcePrefixes"]:
        if any(name.startswith(prefix) for name in client_names):
            raise VerificationError(f"Base contains Advanced client resource prefix {prefix}")
    if "orsc/WorldBuilderInstalledClientProfile.class" not in client_names:
        raise VerificationError("client lacks canonical map startup profile")

    expected_pairing = {
        "artifactContract": "current-platform-runtime-artifact-v1",
        "handshakeId": catalog.platform["protocol"]["handshakeId"],
        "moduleSetHash": supplied["moduleSetHash"],
        "platformManifestHash": supplied["platformManifestHash"],
        "platformReleaseId": supplied["platformReleaseId"],
        "variantId": supplied["variantId"],
        "variantManifestHash": supplied["variantManifestHash"],
    }
    server_pairing = read_pairing(server, "server")
    client_pairing = read_pairing(client, "client")
    sidecar_pairing = parse_pairing(pairing_path.read_bytes(), "sidecar")
    if server_pairing != expected_pairing:
        raise VerificationError("server startup identity differs from composition")
    if client_pairing != expected_pairing:
        raise VerificationError("client startup identity differs from composition")
    if sidecar_pairing != expected_pairing:
        raise VerificationError("startup pairing sidecar differs from composition")
    validate_build_provenance(provenance_path, expected_pairing)

    six_fields = {
        key: supplied[key]
        for key in catalog.platform["protocol"]["identityFields"]
    }
    handshake = hashlib.sha256(composition.canonical_bytes(six_fields)).hexdigest()
    return {
        "status": "verified",
        "variantId": supplied["variantId"],
        "handshakeId": catalog.platform["protocol"]["handshakeId"],
        "artifactPairingSha256": handshake,
        "canonicalMapBootstrap": "verified",
        "publicPluginInventory": "verified",
        "publicStatePolicyContract": "verified",
        "advancedArtifactEffects": "excluded",
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--payload-root", type=Path, default=ROOT)
    return parser.parse_args()


def main() -> int:
    options = parse_arguments()
    try:
        result = verify(options.identity.resolve(), options.payload_root.resolve())
    except (VerificationError, ValueError) as error:
        print(f"Current Base verification failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

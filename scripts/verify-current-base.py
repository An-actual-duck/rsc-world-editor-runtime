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
import xml.etree.ElementTree as ET
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            "clientContent",
            "statePolicy",
            "mapPolicy",
            "serverContent",
            "stateMigration",
            "installedExecutionVerifier",
            "installedLaunch",
            "requiredRuntimeClasses",
            "requiredClientClasses",
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
    if profile["installabilityBlockers"] != []:
        raise VerificationError("installable Current Base still declares blockers")
    if profile["pluginSourceSets"] != ["authentic", "shared"]:
        raise VerificationError("Current Base plugin source sets are not conservative")
    if profile["clientAssetSets"] != ["platform-world-editor-ui"]:
        raise VerificationError("Current Base client asset set is not conservative")
    if profile["clientContent"] != {
        "contentId": "current-base-public-client-content-v1",
        "manifestRole": "client-content-manifest",
        "archiveRole": "client-content",
    }:
        raise VerificationError("Current Base client content binding is incomplete")
    if profile["statePolicy"] != {
        "contractId": "canonical-public-state-v1",
        "durableLocation": "outside-code-runtime",
        "migration": "transactional",
        "rollback": "exact-predecessor",
        "sqliteRootProperty": "openrsc.currentBaseStateRoot",
        "sqliteFile": "current_base.db",
        "sqliteRootPolicy": "required-canonical-private-directory-disjoint-from-runtime",
        "sqliteOpenPolicy": "existing-private-file-read-write-no-create",
    }:
        raise VerificationError("Current Base public state policy is incomplete")
    if profile["mapPolicy"] != {
        "rootProperty": "openrsc.worldBuilderInstalledMapRoot",
        "externalRootPolicy": "canonical-absolute-directory-disjoint-from-runtime",
        "profileBinding": "manifest-sha256-and-package-identity",
        "defaultLocation": "profile-relative-package",
    }:
        raise VerificationError("Current Base installed map location policy is incomplete")
    if profile["serverContent"] != {
        "contentId": "current-base-public-content-v1",
        "manifestRole": "server-content-manifest",
        "archiveRole": "server-content",
        "configurationEntry": "current-base.conf",
        "definitionsRoot": "conf/server",
    }:
        raise VerificationError("Current Base server content binding is incomplete")
    if profile["stateMigration"] != {
        "migrationRowIds": [
            "preservation-retro-sqlite-to-current-base-v1",
            "preservation-core-sqlite-to-current-base-v1",
            "preservation-initialized-sqlite-to-current-base-v1",
            "preservation-retro-mariadb-to-current-base-v1",
        ],
        "manifestRole": "state-migration-manifest",
        "toolArtifactRole": "server-runtime",
        "mainClass": "com.openrsc.server.database.CurrentBaseStateMigration",
        "supportedEngines": ["sqlite", "mariadb"],
    }:
        raise VerificationError("Current Base state migration binding is incomplete")
    if profile["installedExecutionVerifier"] != {
        "verifierId": "current-base-installed-execution-v1",
        "manifestRole": "installed-execution-verifier",
        "toolArtifactRole": "server-runtime",
        "mainClass": "com.openrsc.server.database.CurrentBaseInstalledExecutionVerifier",
        "evidenceSchemaId": "current-base-installed-execution-evidence-v1",
    }:
        raise VerificationError("Current Base installed verifier binding is incomplete")
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


def validate_server_content(manifest_path: Path, archive_path: Path,
                            exclusions: dict[str, bool]) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read server content manifest: {error}") from error
    require_exact_keys(
        manifest,
        {"schemaId", "manifestType", "contentId", "variantId",
         "configurationEntry", "connectionsEntry", "definitionsRoot",
         "definitionLimits", "sourceFiles", "generatedFiles",
         "forbiddenPathFragments"},
        "server content manifest",
    )
    if (manifest["schemaId"] != "current-base-server-content-v1"
            or manifest["manifestType"] != "current-base-server-content"
            or manifest["contentId"] != "current-base-public-content-v1"
            or manifest["variantId"] != "current-base-v1"):
        raise VerificationError("server content manifest has wrong identity")
    expected = {manifest["configurationEntry"], manifest["connectionsEntry"]}
    for record in manifest["sourceFiles"]:
        require_exact_keys(record, {"sourcePath", "bundlePath", "transform"},
                           "server content source")
        expected.add(record["bundlePath"])
    generated = {}
    for record in manifest["generatedFiles"]:
        require_exact_keys(record, {"bundlePath", "content"},
                           "server generated content")
        expected.add(record["bundlePath"])
        generated[record["bundlePath"]] = record["content"].encode("utf-8")
    if len(expected) != 2 + len(manifest["sourceFiles"]) + len(generated):
        raise VerificationError("server content manifest has duplicate paths")
    names = archive_names(archive_path)
    if names != expected:
        raise VerificationError("server content archive differs from its closed inventory")
    for name in names:
        if any(fragment.casefold() in name.casefold()
               for fragment in manifest["forbiddenPathFragments"]):
            raise VerificationError(f"Advanced-only server content path is present: {name}")
    with zipfile.ZipFile(archive_path) as archive:
        for name, payload in generated.items():
            if archive.read(name) != payload:
                raise VerificationError(f"generated server content differs: {name}")
        items = json.loads(archive.read("conf/server/defs/ItemDefs.json"))["item"]
        npcs = json.loads(archive.read("conf/server/defs/NpcDefs.json"))["npcs"]
        limits = manifest["definitionLimits"]
        if [row["id"] for row in items] != list(range(limits["itemMaxId"] + 1)):
            raise VerificationError("Base item definitions are not the vanilla ID prefix")
        if [row["id"] for row in npcs] != list(range(limits["npcMaxId"] + 1)):
            raise VerificationError("Base NPC definitions are not the vanilla ID prefix")
        doors = ET.fromstring(archive.read("conf/server/defs/DoorDef.xml"))
        scenery = ET.fromstring(archive.read("conf/server/defs/GameObjectDef.xml"))
        if len(list(doors)) != limits["boundaryMaxId"] + 1:
            raise VerificationError("Base boundary definitions exceed the vanilla prefix")
        if len(list(scenery)) != limits["sceneryMaxId"] + 1:
            raise VerificationError("Base scenery definitions exceed the vanilla prefix")
        config = archive.read(manifest["configurationEntry"]).decode("utf-8")
    configured = {}
    for line in config.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        if value.strip():
            configured[key.strip()] = value.strip()
    for key, expected_value in exclusions.items():
        if configured.get(key) != str(expected_value).lower():
            raise VerificationError(f"Base server content does not disable {key}")


def validate_state_migration(path: Path, profile: dict) -> dict:
    try:
        migration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read state migration manifest: {error}") from error
    require_exact_keys(
        migration,
        {"schemaId", "manifestType", "migrationRows", "targetStateContractId",
         "supportedSources", "transformations", "resourceLimits", "invocation",
         "evidenceContract"},
        "state migration manifest",
    )
    binding = profile["stateMigration"]
    if (migration["schemaId"] != "current-base-state-migration-v1"
            or migration["manifestType"] != "current-base-state-migration"
            or migration["migrationRows"] != binding["migrationRowIds"]
            or migration["targetStateContractId"] != "canonical-public-state-v1"):
        raise VerificationError("state migration manifest has wrong identity")
    sources = migration["supportedSources"]
    source_engines = []
    for row in sources:
        if row.get("engine") not in source_engines:
            source_engines.append(row.get("engine"))
    if source_engines != binding["supportedEngines"]:
        raise VerificationError("state migration engines differ from profile")
    if [row.get("migrationRowId") for row in sources] != binding["migrationRowIds"]:
        raise VerificationError("state migration source rows differ from profile")
    for row in sources:
        require_exact_keys(
            row,
            {"migrationRowId", "engine", "sourceSchemaId", "sourceSchemaFingerprint",
             "sourceSchemaFingerprintAlgorithm", "verificationRuntime",
             "stageMode", "sourceMutation",
             "rollback", "credentialPolicy", "transformationId"},
            "state migration engine",
        )
        fingerprint = row["sourceSchemaFingerprint"]
        if (not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in fingerprint)):
            raise VerificationError("state migration schema fingerprint is malformed")
    invocation = migration["invocation"]
    require_exact_keys(invocation, {"toolArtifactRole", "mainClass", "arguments"},
                       "state migration invocation")
    if (invocation["toolArtifactRole"] != binding["toolArtifactRole"]
            or invocation["mainClass"] != binding["mainClass"]):
        raise VerificationError("state migration invocation differs from profile")
    return migration


def validate_installed_verifier(path: Path, profile: dict) -> None:
    try:
        verifier = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read installed verifier contract: {error}") from error
    require_exact_keys(
        verifier,
        {"schemaId", "manifestType", "verifierId", "invocation",
         "executionPolicy", "isolationPolicy", "supervisionPolicy", "requiredObservations",
         "evidenceContract", "exitSemantics", "recoveryPolicy"},
        "installed verifier contract",
    )
    binding = profile["installedExecutionVerifier"]
    if (verifier["schemaId"] != "current-base-installed-execution-v1"
            or verifier["manifestType"] != "current-base-installed-execution-verifier"
            or verifier["verifierId"] != binding["verifierId"]):
        raise VerificationError("installed verifier contract has wrong identity")
    invocation = verifier["invocation"]
    if (invocation.get("toolArtifactRole") != binding["toolArtifactRole"]
            or invocation.get("mainClass") != binding["mainClass"]):
        raise VerificationError("installed verifier invocation differs from profile")
    if verifier["evidenceContract"].get("schemaId") != binding["evidenceSchemaId"]:
        raise VerificationError("installed verifier evidence differs from profile")


def validate_input_adapter(path: Path, baseline_path: Path,
                           converter_path: Path) -> None:
    adapter = json.loads(path.read_text(encoding="utf-8"))
    require_exact_keys(
        adapter,
        {"schemaId", "manifestType", "inputAdapterId", "inputAdapterContractId",
         "sourceLineage", "baseline", "targetLayout", "configurationSelectors",
         "mapConversion", "stateRows", "selectionPolicy"},
        "input adapter",
    )
    if (adapter["schemaId"] != "current-preservation-r64-input-adapter-v1"
            or adapter["manifestType"] != "current-platform-input-adapter"
            or adapter["inputAdapterId"] != "preservation-r64-sqlite-v1"):
        raise VerificationError("input adapter has wrong identity")
    if file_sha256(baseline_path) != adapter["baseline"]["sha256"]:
        raise VerificationError("input adapter baseline hash differs")
    conversion = adapter["mapConversion"]
    if (conversion.get("toolArtifactRole") != "input-adapter-map-converter"
            or conversion.get("mainClass") != "com.openrsc.layeredmaps.LayeredMapsCli"
            or conversion.get("command") != "preservation-package"
            or conversion.get("outputReviewState") != "transitions-pending"
            or conversion.get("runtimePromotionApproved") is not False):
        raise VerificationError("input adapter map conversion is unsupported")
    if "com/openrsc/layeredmaps/LayeredMapsCli.class" not in archive_names(converter_path):
        raise VerificationError("input adapter converter lacks its declared main class")


def validate_client_content(manifest_path: Path, archive_path: Path) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read client content manifest: {error}") from error
    require_exact_keys(
        manifest,
        {"schemaId", "manifestType", "contentId", "variantId", "sourceTrees",
         "sourceFiles", "forbiddenPathFragments"},
        "client content manifest",
    )
    if (manifest["schemaId"] != "current-base-client-content-v1"
            or manifest["manifestType"] != "current-base-client-content"
            or manifest["contentId"] != "current-base-public-client-content-v1"
            or manifest["variantId"] != "current-base-v1"):
        raise VerificationError("client content manifest has wrong identity")
    expected: set[str] = set()
    for tree in manifest["sourceTrees"]:
        require_exact_keys(tree, {"sourcePath", "bundlePath"},
                           "client content source tree")
        source_root = ROOT / tree["sourcePath"]
        for source in source_root.rglob("*"):
            if source.is_file() and not source.is_symlink():
                expected.add(
                    tree["bundlePath"] + "/" + source.relative_to(source_root).as_posix()
                )
    for record in manifest["sourceFiles"]:
        require_exact_keys(record, {"sourcePath", "bundlePath"},
                           "client content source file")
        expected.add(record["bundlePath"])
    names = archive_names(archive_path)
    if names != expected:
        raise VerificationError("client content archive differs from its closed inventory")
    for name in names:
        if any(fragment.casefold() in name.casefold()
               for fragment in manifest["forbiddenPathFragments"]):
            raise VerificationError(f"Advanced-only client content is present: {name}")


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
    if supplied["variantId"] != "current-base-v1" or not supplied["installable"]:
        raise VerificationError("composition is not the installable Current Base candidate")

    server = inventory_path(supplied, "server-runtime", payload_root)
    plugins = inventory_path(supplied, "server-plugins", payload_root)
    client = inventory_path(supplied, "client-runtime", payload_root)
    profile_path = inventory_path(supplied, "runtime-profile", payload_root)
    pairing_path = inventory_path(supplied, "server-client-pairing", payload_root)
    provenance_path = inventory_path(supplied, "build-provenance", payload_root)
    content_manifest_path = inventory_path(
        supplied, "server-content-manifest", payload_root)
    content_path = inventory_path(supplied, "server-content", payload_root)
    migration_path = inventory_path(
        supplied, "state-migration-manifest", payload_root)
    installed_verifier_path = inventory_path(
        supplied, "installed-execution-verifier", payload_root)
    input_adapter_path = inventory_path(
        supplied, "input-adapter-manifest", payload_root)
    input_baseline_path = inventory_path(
        supplied, "input-adapter-baseline", payload_root)
    input_converter_path = inventory_path(
        supplied, "input-adapter-map-converter", payload_root)
    client_content_manifest_path = inventory_path(
        supplied, "client-content-manifest", payload_root)
    client_content_path = inventory_path(supplied, "client-content", payload_root)
    server_names = archive_names(server)
    plugin_names = archive_names(plugins)
    client_names = archive_names(client)
    profile = validate_profile(profile_path)
    validate_server_content(
        content_manifest_path, content_path,
        profile["advancedExclusions"]["configuration"])
    migration = validate_state_migration(migration_path, profile)
    validate_installed_verifier(installed_verifier_path, profile)
    validate_input_adapter(
        input_adapter_path, input_baseline_path, input_converter_path)
    validate_client_content(client_content_manifest_path, client_content_path)

    for required in profile["requiredRuntimeClasses"]:
        if required not in server_names:
            raise VerificationError(f"server lacks canonical runtime class {required}")
    for required in profile["requiredClientClasses"]:
        if required not in client_names:
            raise VerificationError(f"client lacks required runtime class {required}")
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
        "stateMigrationContracts": migration["migrationRows"],
        "installedExecutionVerifier": "verified",
        "inputAdapter": "verified",
        "serverContent": "verified",
        "clientContent": "verified",
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

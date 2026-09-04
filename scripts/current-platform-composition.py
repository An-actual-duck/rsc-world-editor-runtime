#!/usr/bin/env python3
"""Validate and resolve current-platform composition contracts.

This tool deliberately operates on provider-owned manifests and staged payloads.
It never discovers or executes historical target code, and a target receipt is
never accepted as build or artifact evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "current-platform"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
MODULE_NAMESPACE_ROOT = "org/rscworld/modules"
FORBIDDEN_MODULE_CLASS_PREFIXES = (
    "com/openrsc/",
    "orsc/",
    "org/apache/",
    "com/google/",
)


class ContractError(ValueError):
    """Raised when a current-platform contract fails closed."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read JSON contract {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"contract must be a JSON object: {path}")
    return value


def require_exact_keys(value: dict, required: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - required)
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unknown " + ", ".join(extra))
        raise ContractError(f"{label} has invalid keys ({'; '.join(details)})")


def require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ContractError(f"{label} must be a lowercase hyphenated identifier")
    return value


def require_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"{label} must be an array of strings")
    if len(value) != len(set(value)):
        raise ContractError(f"{label} contains duplicates")
    return value


def require_safe_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} must be a non-empty relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "\\" in value
        or any(part in ("", ".", "..") for part in path.parts)
        or path.as_posix() != value
    ):
        raise ContractError(f"{label} is not a normalized safe relative path: {value}")
    return value


def validate_platform(value: dict) -> None:
    require_exact_keys(
        value,
        {
            "schemaId",
            "manifestType",
            "platformReleaseId",
            "platformGeneration",
            "platformApiVersion",
            "extensionApi",
            "protocol",
            "schemaContracts",
            "mapRuntimeCapabilities",
            "inputAdapterBoundary",
            "bundleContract",
            "provenance",
        },
        "platform release",
    )
    if value["schemaId"] != "current-platform-release-v1":
        raise ContractError("platform release has the wrong schemaId")
    if value["manifestType"] != "current-platform-release":
        raise ContractError("platform release has the wrong manifestType")
    require_id(value["platformReleaseId"], "platformReleaseId")
    if not isinstance(value["platformGeneration"], int) or value["platformGeneration"] < 1:
        raise ContractError("platformGeneration must be a positive integer")
    require_id(value["platformApiVersion"], "platformApiVersion")
    protocol = value["protocol"]
    require_exact_keys(
        protocol,
        {"handshakeId", "mismatchPolicy", "identityFields"},
        "protocol",
    )
    if protocol["mismatchPolicy"] != "refuse-startup":
        raise ContractError("protocol mismatch policy must refuse startup")
    expected_identity_fields = [
        "platformReleaseId",
        "platformManifestHash",
        "variantId",
        "variantManifestHash",
        "moduleSetHash",
        "bundleInventoryHash",
    ]
    if protocol["identityFields"] != expected_identity_fields:
        raise ContractError("protocol must carry the canonical six-field identity")
    schema_contracts = value["schemaContracts"]
    if not isinstance(schema_contracts, list) or not schema_contracts:
        raise ContractError("schemaContracts must be a non-empty array")
    schema_ids = []
    for record in schema_contracts:
        if not isinstance(record, dict):
            raise ContractError("schemaContracts entries must be objects")
        require_exact_keys(record, {"schemaId", "relativePath", "sha256"}, "schema contract")
        schema_ids.append(require_id(record["schemaId"], "schema contract schemaId"))
        require_safe_relative_path(record["relativePath"], "schema contract relativePath")
        if not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise ContractError("schema contract sha256 must be a lowercase SHA-256")
    if len(schema_ids) != len(set(schema_ids)):
        raise ContractError("schemaContracts contains duplicate schema IDs")
    if schema_ids != sorted(schema_ids):
        raise ContractError("schemaContracts must be ordered by schemaId")
    require_string_list(value["mapRuntimeCapabilities"], "mapRuntimeCapabilities")
    boundary = value["inputAdapterBoundary"]
    require_exact_keys(
        boundary,
        {"contractId", "installedInRuntime", "selectionAuthority", "unknownCodePolicy"},
        "inputAdapterBoundary",
    )
    if boundary["installedInRuntime"] is not False:
        raise ContractError("input adapters must not be installed in the current runtime")
    if boundary["selectionAuthority"] != "editor-migration-boundary-only":
        raise ContractError("input adapters cannot select installed runtime behavior")
    if boundary["unknownCodePolicy"] != "refuse-before-mutation":
        raise ContractError("unknown target code must fail before mutation")
    extension = value["extensionApi"]
    require_exact_keys(
        extension,
        {"apiId", "allowedModuleNamespaceRoot", "forbiddenClassPrefixes", "classShadowPolicy"},
        "extensionApi",
    )
    if extension["allowedModuleNamespaceRoot"] != MODULE_NAMESPACE_ROOT.replace("/", "."):
        raise ContractError("extension API has an unexpected module namespace")
    if extension["classShadowPolicy"] != "forbid":
        raise ContractError("module class shadowing must be forbidden")
    require_string_list(extension["forbiddenClassPrefixes"], "forbiddenClassPrefixes")
    bundle = value["bundleContract"]
    require_exact_keys(
        bundle,
        {
            "schemaId",
            "closedInventoryRequired",
            "artifactHashAlgorithm",
            "sourceAuthority",
            "receiptBuildAuthority",
            "targetOverlayPolicy",
            "activationLayout",
        },
        "bundleContract",
    )
    if bundle["closedInventoryRequired"] is not True:
        raise ContractError("current bundles require a closed inventory")
    if bundle["artifactHashAlgorithm"] != "sha256":
        raise ContractError("current bundle artifact hashing must use SHA-256")
    if bundle["sourceAuthority"] != "selected-current-composition-source":
        raise ContractError("bundle source authority cannot be a generic pinned core")
    if bundle["receiptBuildAuthority"] != "never":
        raise ContractError("receipt existence cannot suppress source builds")
    if bundle["targetOverlayPolicy"] != "replace-complete-runtime-no-class-overlay":
        raise ContractError("current bundles cannot overlay old target classes")
    if bundle["activationLayout"] != "side-by-side-content-addressed":
        raise ContractError("current bundles require side-by-side activation")
    provenance = value["provenance"]
    require_exact_keys(
        provenance,
        {"repository", "authority", "historicalTargetCodeAllowed"},
        "platform provenance",
    )
    if provenance != {
        "repository": "rsc-world-editor-runtime",
        "authority": "provider-commit",
        "historicalTargetCodeAllowed": False,
    }:
        raise ContractError("platform provenance must remain provider-owned")


def validate_variant(value: dict, platform: dict) -> None:
    require_exact_keys(
        value,
        {
            "schemaId",
            "manifestType",
            "variantId",
            "displayName",
            "platformReleaseId",
            "variantRole",
            "releaseStatus",
            "installable",
            "defaultModuleIds",
            "requiredCapabilities",
            "forbiddenCapabilities",
            "advancedOnlyCapabilities",
            "inputAdapterRecommendations",
            "serverClientPairing",
            "retirementPath",
            "provenance",
        },
        "variant",
    )
    if value["schemaId"] != "current-variant-v1":
        raise ContractError("variant has the wrong schemaId")
    if value["manifestType"] != "current-platform-variant":
        raise ContractError("variant has the wrong manifestType")
    require_id(value["variantId"], "variantId")
    if value["platformReleaseId"] != platform["platformReleaseId"]:
        raise ContractError("variant platformReleaseId does not match the platform")
    if value["releaseStatus"] not in (
        "foundation-contract-only", "artifact-candidate", "release-candidate", "released"
    ):
        raise ContractError("variant has an unknown releaseStatus")
    if not isinstance(value["installable"], bool):
        raise ContractError("variant installable must be boolean")
    if value["installable"] and value["releaseStatus"] == "foundation-contract-only":
        raise ContractError("a foundation-only variant cannot be installable")
    for field in (
        "defaultModuleIds",
        "requiredCapabilities",
        "forbiddenCapabilities",
        "advancedOnlyCapabilities",
        "inputAdapterRecommendations",
    ):
        require_string_list(value[field], field)
    overlap = set(value["requiredCapabilities"]) & set(value["forbiddenCapabilities"])
    if overlap:
        raise ContractError("variant both requires and forbids: " + ", ".join(sorted(overlap)))
    pairing = value["serverClientPairing"]
    require_exact_keys(
        pairing,
        {"required", "handshakeId", "mismatchPolicy"},
        "serverClientPairing",
    )
    if pairing["required"] is not True or pairing["mismatchPolicy"] != "refuse-startup":
        raise ContractError("variant must fail closed on a server/client mismatch")
    if pairing["handshakeId"] != platform["protocol"]["handshakeId"]:
        raise ContractError("variant handshake does not match the platform")
    provenance = value["provenance"]
    require_exact_keys(
        provenance,
        {"repository", "authority", "contentPolicy"},
        "variant provenance",
    )
    if provenance["repository"] != "rsc-world-editor-runtime":
        raise ContractError("variant provenance names another repository")
    if provenance["authority"] != "provider-commit":
        raise ContractError("variant provenance is not provider-owned")


MODULE_KEYS = {
    "schemaId",
    "manifestType",
    "moduleId",
    "moduleVersion",
    "kind",
    "platformReleaseId",
    "platformApiVersion",
    "providesCapabilities",
    "requires",
    "conflicts",
    "loadAfter",
    "loadBefore",
    "entryPoints",
    "configurationNamespaces",
    "stateMigrations",
    "clientPairing",
    "artifacts",
    "semanticTests",
    "provenance",
}

ARTIFACT_KEYS = {
    "sourcePath",
    "bundlePath",
    "role",
    "destination",
    "ownership",
    "replacementPolicy",
    "rollbackPolicy",
    "provenance",
}


def validate_artifact_spec(value: dict, label: str) -> None:
    require_exact_keys(value, ARTIFACT_KEYS, label)
    require_safe_relative_path(value["sourcePath"], f"{label}.sourcePath")
    require_safe_relative_path(value["bundlePath"], f"{label}.bundlePath")
    require_safe_relative_path(value["destination"], f"{label}.destination")
    for field in ("role", "ownership", "replacementPolicy", "rollbackPolicy", "provenance"):
        require_id(value[field], f"{label}.{field}")


def validate_module(value: dict, platform: dict) -> None:
    require_exact_keys(value, MODULE_KEYS, "module")
    if value["schemaId"] != "current-module-v1":
        raise ContractError("module has the wrong schemaId")
    if value["manifestType"] != "current-platform-module":
        raise ContractError("module has the wrong manifestType")
    module_id = require_id(value["moduleId"], "moduleId")
    if value["platformReleaseId"] != platform["platformReleaseId"]:
        raise ContractError(f"module {module_id} targets another platform release")
    if value["platformApiVersion"] != platform["platformApiVersion"]:
        raise ContractError(f"module {module_id} targets another platform API")
    if value["kind"] not in ("declarative-data", "code-plugin", "coordinated-server-client"):
        raise ContractError(f"module {module_id} has an unknown kind")
    for field in (
        "providesCapabilities",
        "conflicts",
        "loadAfter",
        "loadBefore",
        "entryPoints",
        "configurationNamespaces",
        "stateMigrations",
        "semanticTests",
    ):
        require_string_list(value[field], f"module {module_id} {field}")
    if not isinstance(value["requires"], list):
        raise ContractError(f"module {module_id} requires must be an array")
    required_ids = []
    for index, requirement in enumerate(value["requires"]):
        if not isinstance(requirement, dict):
            raise ContractError(f"module {module_id} requirement {index} must be an object")
        require_exact_keys(requirement, {"moduleId", "moduleVersion"}, "module requirement")
        required_ids.append(require_id(requirement["moduleId"], "required moduleId"))
        if not isinstance(requirement["moduleVersion"], str) or not requirement["moduleVersion"]:
            raise ContractError("required moduleVersion must be non-empty")
    if len(required_ids) != len(set(required_ids)):
        raise ContractError(f"module {module_id} has duplicate requirements")
    pairing = value["clientPairing"]
    require_exact_keys(pairing, {"required", "clientCapabilityId"}, "module clientPairing")
    if not isinstance(pairing["required"], bool):
        raise ContractError("module clientPairing.required must be boolean")
    if pairing["required"] and not pairing["clientCapabilityId"]:
        raise ContractError("paired module is missing clientCapabilityId")
    if not pairing["required"] and pairing["clientCapabilityId"] is not None:
        raise ContractError("unpaired module must use a null clientCapabilityId")
    if pairing["clientCapabilityId"] is not None:
        require_id(pairing["clientCapabilityId"], "module clientCapabilityId")
    if not isinstance(value["artifacts"], list) or not value["artifacts"]:
        raise ContractError(f"module {module_id} must declare at least one artifact")
    bundle_paths = []
    for index, artifact in enumerate(value["artifacts"]):
        if not isinstance(artifact, dict):
            raise ContractError(f"module {module_id} artifact {index} must be an object")
        validate_artifact_spec(artifact, f"module {module_id} artifact {index}")
        bundle_paths.append(artifact["bundlePath"])
    if len(bundle_paths) != len(set(bundle_paths)):
        raise ContractError(f"module {module_id} has duplicate bundle paths")
    expected_namespace = f"{MODULE_NAMESPACE_ROOT}/{module_id.replace('-', '_')}/"
    for entry_point in value["entryPoints"]:
        class_path = entry_point.replace(".", "/") + ".class"
        if not class_path.startswith(expected_namespace):
            raise ContractError(
                f"module {module_id} entry point is outside its namespace: {entry_point}"
            )
    for namespace in value["configurationNamespaces"]:
        if not namespace.startswith(module_id + "."):
            raise ContractError(
                f"module {module_id} configuration namespace is not owned by it: {namespace}"
            )
    provenance = value["provenance"]
    require_exact_keys(provenance, {"kind", "redistributable"}, "module provenance")
    if provenance["kind"] not in (
        "provider-commit",
        "sealed-synthetic-fixture",
        "target-derived-local",
    ):
        raise ContractError(f"module {module_id} has unknown provenance kind")
    if not isinstance(provenance["redistributable"], bool):
        raise ContractError(f"module {module_id} redistributable must be boolean")
    if provenance["kind"] == "target-derived-local" and provenance["redistributable"]:
        raise ContractError("target-derived local modules cannot be redistributable")


def validate_bundle_spec(value: dict, platform: dict, variant: dict) -> None:
    require_exact_keys(
        value,
        {
            "schemaId",
            "manifestType",
            "bundleSpecId",
            "platformReleaseId",
            "variantId",
            "moduleIds",
            "inputAdapterContractId",
            "installable",
            "buildPolicy",
            "durableStatePolicy",
            "artifacts",
            "requiredExecutableScenarios",
        },
        "bundle spec",
    )
    if value["schemaId"] != "current-bundle-spec-v1":
        raise ContractError("bundle spec has the wrong schemaId")
    if value["manifestType"] != "current-platform-bundle-spec":
        raise ContractError("bundle spec has the wrong manifestType")
    require_id(value["bundleSpecId"], "bundleSpecId")
    if value["platformReleaseId"] != platform["platformReleaseId"]:
        raise ContractError("bundle spec platform does not match")
    if value["variantId"] != variant["variantId"]:
        raise ContractError("bundle spec variant does not match")
    if value["installable"] != variant["installable"]:
        raise ContractError("bundle and variant installable states disagree")
    require_string_list(value["moduleIds"], "bundle moduleIds")
    if value["moduleIds"] != variant["defaultModuleIds"]:
        raise ContractError("bundle moduleIds must equal the variant default module set")
    build = value["buildPolicy"]
    require_exact_keys(
        build,
        {"sourceAuthority", "rebuildPolicy", "receiptAuthority", "targetCorePolicy"},
        "buildPolicy",
    )
    if build != {
        "sourceAuthority": "selected-current-composition-source",
        "rebuildPolicy": "build-and-verify-before-packaging",
        "receiptAuthority": "never",
        "targetCorePolicy": "replace-complete-runtime-no-overlay",
    }:
        raise ContractError("bundle build policy permits pinned-core or receipt authority")
    durable = value["durableStatePolicy"]
    require_exact_keys(
        durable,
        {"location", "replacementPolicy", "rollbackPolicy"},
        "durableStatePolicy",
    )
    if durable != {
        "location": "outside-code-runtime",
        "replacementPolicy": "migrate-transactionally",
        "rollbackPolicy": "restore-exact-predecessor",
    }:
        raise ContractError("bundle durable state policy is not transaction-safe")
    if not isinstance(value["artifacts"], list) or not value["artifacts"]:
        raise ContractError("bundle spec must declare artifacts")
    bundle_paths = []
    for index, artifact in enumerate(value["artifacts"]):
        if not isinstance(artifact, dict):
            raise ContractError(f"bundle artifact {index} must be an object")
        validate_artifact_spec(artifact, f"bundle artifact {index}")
        bundle_paths.append(artifact["bundlePath"])
    if len(bundle_paths) != len(set(bundle_paths)):
        raise ContractError("bundle spec contains duplicate bundle paths")
    require_string_list(value["requiredExecutableScenarios"], "requiredExecutableScenarios")


class Catalog:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.platform_path = self.root / "platform/current-platform-r1.json"
        self.platform = load_json(self.platform_path)
        validate_platform(self.platform)
        self.variants: dict[str, tuple[Path, dict]] = {}
        for path in sorted((self.root / "variants").glob("*.json")):
            variant = load_json(path)
            validate_variant(variant, self.platform)
            variant_id = variant["variantId"]
            if variant_id in self.variants:
                raise ContractError(f"duplicate variantId: {variant_id}")
            self.variants[variant_id] = (path, variant)
        self.modules: dict[str, tuple[Path, dict]] = {}
        module_dir = self.root / "modules"
        if module_dir.is_dir():
            for path in sorted(module_dir.glob("*.json")):
                module = load_json(path)
                validate_module(module, self.platform)
                module_id = module["moduleId"]
                if module_id in self.modules:
                    raise ContractError(f"duplicate moduleId: {module_id}")
                self.modules[module_id] = (path, module)
        self.bundle_specs: dict[str, tuple[Path, dict]] = {}
        for path in sorted((self.root / "bundle-specs").glob("*.json")):
            spec = load_json(path)
            variant_id = spec.get("variantId")
            if variant_id not in self.variants:
                raise ContractError(f"bundle spec names unknown variant: {variant_id}")
            validate_bundle_spec(spec, self.platform, self.variants[variant_id][1])
            if variant_id in self.bundle_specs:
                raise ContractError(f"duplicate bundle spec for variant: {variant_id}")
            self.bundle_specs[variant_id] = (path, spec)
        if set(self.bundle_specs) != set(self.variants):
            raise ContractError("every variant must have exactly one bundle spec")


def resolve_modules(catalog: Catalog, selected: list[str]) -> list[dict]:
    if len(selected) != len(set(selected)):
        raise ContractError("selected module IDs contain duplicates")
    closure: dict[str, dict] = {}
    visiting: set[str] = set()

    def include(module_id: str) -> None:
        if module_id in closure:
            return
        if module_id in visiting:
            raise ContractError(f"module dependency cycle includes {module_id}")
        if module_id not in catalog.modules:
            raise ContractError(f"unknown module: {module_id}")
        visiting.add(module_id)
        module = catalog.modules[module_id][1]
        for requirement in module["requires"]:
            required_id = requirement["moduleId"]
            include(required_id)
            actual_version = closure[required_id]["moduleVersion"]
            if actual_version != requirement["moduleVersion"]:
                raise ContractError(
                    f"module {module_id} requires {required_id} "
                    f"{requirement['moduleVersion']}, found {actual_version}"
                )
        visiting.remove(module_id)
        closure[module_id] = module

    for module_id in selected:
        include(module_id)
    for module_id, module in closure.items():
        conflicts = set(module["conflicts"]) & set(closure)
        if conflicts:
            raise ContractError(
                f"module {module_id} conflicts with " + ", ".join(sorted(conflicts))
            )

    edges: dict[str, set[str]] = {module_id: set() for module_id in closure}
    incoming: dict[str, int] = {module_id: 0 for module_id in closure}

    def add_edge(before: str, after: str, reason: str) -> None:
        if before not in closure or after not in closure:
            return
        if before == after:
            raise ContractError(f"module {before} has a self-order constraint ({reason})")
        if after not in edges[before]:
            edges[before].add(after)
            incoming[after] += 1

    for module_id, module in closure.items():
        for requirement in module["requires"]:
            add_edge(requirement["moduleId"], module_id, "dependency")
        for before in module["loadAfter"]:
            if before not in closure:
                raise ContractError(f"module {module_id} loadAfter names unselected {before}")
            add_edge(before, module_id, "loadAfter")
        for after in module["loadBefore"]:
            if after not in closure:
                raise ContractError(f"module {module_id} loadBefore names unselected {after}")
            add_edge(module_id, after, "loadBefore")

    ready = sorted(module_id for module_id, count in incoming.items() if count == 0)
    ordered: list[dict] = []
    while ready:
        module_id = ready.pop(0)
        ordered.append(closure[module_id])
        for after in sorted(edges[module_id]):
            incoming[after] -= 1
            if incoming[after] == 0:
                ready.append(after)
                ready.sort()
    if len(ordered) != len(closure):
        blocked = sorted(module_id for module_id, count in incoming.items() if count)
        raise ContractError("module ordering cycle includes " + ", ".join(blocked))
    return ordered


def inspect_module_archive(path: Path, module_id: str) -> None:
    if not zipfile.is_zipfile(path):
        return
    expected = f"{MODULE_NAMESPACE_ROOT}/{module_id.replace('-', '_')}/"
    with zipfile.ZipFile(path) as archive:
        exact_names: set[str] = set()
        folded_names: set[str] = set()
        for info in archive.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            safe_name = require_safe_relative_path(name, f"archive entry in {path.name}")
            if safe_name in exact_names:
                raise ContractError(
                    f"module {module_id} archive contains a duplicate entry: {safe_name}"
                )
            folded = safe_name.casefold()
            if folded in folded_names:
                raise ContractError(
                    f"module {module_id} archive contains a case-fold collision: {safe_name}"
                )
            exact_names.add(safe_name)
            folded_names.add(folded)
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(unix_mode) == stat.S_IFLNK:
                raise ContractError(
                    f"module {module_id} archive contains a symbolic link: {safe_name}"
                )
            if safe_name == "META-INF/MANIFEST.MF":
                continue
            if not safe_name.startswith(expected):
                if safe_name.endswith(".class") and safe_name.startswith(
                    FORBIDDEN_MODULE_CLASS_PREFIXES
                ):
                    raise ContractError(
                        f"module {module_id} archive shadows a platform/dependency class: {safe_name}"
                    )
                raise ContractError(
                    f"module {module_id} archive entry is outside its namespace: {safe_name}"
                )
            if not safe_name.endswith(".class"):
                continue
            if safe_name.startswith(FORBIDDEN_MODULE_CLASS_PREFIXES):
                raise ContractError(
                    f"module {module_id} archive shadows a platform/dependency class: {safe_name}"
                )


def inventory_artifacts(
    payload_root: Path, artifacts: list[dict], module_id: str | None = None
) -> list[dict]:
    root = payload_root.resolve()
    inventory = []
    for spec in artifacts:
        candidate = root / spec["sourcePath"]
        cursor = root
        for part in PurePosixPath(spec["sourcePath"]).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ContractError(
                    f"artifact path must not contain a symbolic link: {spec['sourcePath']}"
                )
        source = candidate.resolve()
        try:
            source.relative_to(root)
        except ValueError as error:
            raise ContractError(f"artifact escapes payload root: {spec['sourcePath']}") from error
        if not source.is_file():
            raise ContractError(f"artifact is missing or not a file: {spec['sourcePath']}")
        if module_id is not None:
            inspect_module_archive(source, module_id)
        mode = stat.S_IMODE(source.stat().st_mode)
        inventory.append(
            {
                "bundlePath": spec["bundlePath"],
                "destination": spec["destination"],
                "mode": format(mode, "04o"),
                "ownership": spec["ownership"],
                "provenance": spec["provenance"],
                "replacementPolicy": spec["replacementPolicy"],
                "role": spec["role"],
                "rollbackPolicy": spec["rollbackPolicy"],
                "sha256": file_hash(source),
                "size": source.stat().st_size,
                "type": "file",
            }
        )
    inventory.sort(key=lambda item: item["bundlePath"])
    paths = [item["bundlePath"] for item in inventory]
    if len(paths) != len(set(paths)):
        raise ContractError("resolved artifact inventory contains duplicate bundle paths")
    return inventory


def resolve_composition(
    catalog: Catalog, variant_id: str, selected_modules: list[str], payload_root: Path
) -> dict:
    if variant_id not in catalog.variants:
        raise ContractError(f"unknown variant: {variant_id}")
    variant_path, variant = catalog.variants[variant_id]
    spec_path, spec = catalog.bundle_specs[variant_id]
    requested = list(variant["defaultModuleIds"])
    for module_id in selected_modules:
        if module_id not in requested:
            requested.append(module_id)
    modules = resolve_modules(catalog, requested)
    inventory = inventory_artifacts(payload_root, spec["artifacts"])
    module_hash_records = []
    for module in modules:
        module_path = catalog.modules[module["moduleId"]][0]
        module_inventory = inventory_artifacts(
            payload_root, module["artifacts"], module["moduleId"]
        )
        existing_paths = {item["bundlePath"] for item in inventory}
        collisions = existing_paths & {item["bundlePath"] for item in module_inventory}
        if collisions:
            raise ContractError(
                f"module {module['moduleId']} collides with bundle paths: "
                + ", ".join(sorted(collisions))
            )
        inventory.extend(module_inventory)
        payload_root_hash = canonical_hash(module_inventory)
        module_hash_records.append(
            {
                "manifestHash": canonical_hash(load_json(module_path)),
                "moduleId": module["moduleId"],
                "moduleVersion": module["moduleVersion"],
                "payloadRootHash": payload_root_hash,
            }
        )
    inventory.sort(key=lambda item: item["bundlePath"])
    module_set_hash = canonical_hash(module_hash_records)
    bundle_inventory_hash = canonical_hash(inventory)
    result = {
        "schemaId": "current-composition-identity-v1",
        "manifestType": "current-platform-composition-identity",
        "platformReleaseId": catalog.platform["platformReleaseId"],
        "platformManifestHash": canonical_hash(load_json(catalog.platform_path)),
        "schemaSetHash": canonical_hash(catalog.platform["schemaContracts"]),
        "variantId": variant_id,
        "variantManifestHash": canonical_hash(load_json(variant_path)),
        "moduleSetHash": module_set_hash,
        "bundleInventoryHash": bundle_inventory_hash,
        "moduleSet": module_hash_records,
        "bundleInventory": inventory,
        "bundleSpecId": spec["bundleSpecId"],
        "bundleSpecHash": canonical_hash(load_json(spec_path)),
        "inputAdapterContractId": spec["inputAdapterContractId"],
        "installable": spec["installable"],
    }
    return result


def verify_schema_bindings(catalog: Catalog) -> None:
    schema_ids = {
        "current-base-runtime-profile-v1": "current-base-runtime-profile-v1.schema.json",
        "current-platform-release-v1": "current-platform-release-v1.schema.json",
        "current-variant-v1": "current-variant-v1.schema.json",
        "current-module-v1": "current-module-v1.schema.json",
        "current-bundle-spec-v1": "current-bundle-spec-v1.schema.json",
        "current-composition-identity-v1": "current-composition-identity-v1.schema.json",
    }
    records = {
        record["schemaId"]: record for record in catalog.platform["schemaContracts"]
    }
    if set(records) != set(schema_ids):
        raise ContractError("platform schemaContracts does not name the complete schema set")
    for schema_id, filename in schema_ids.items():
        path = catalog.root / "schema" / filename
        schema = load_json(path)
        if schema.get("$id") != schema_id:
            raise ContractError(f"schema {filename} does not bind $id {schema_id}")
        if schema.get("additionalProperties") is not False:
            raise ContractError(f"schema {filename} must reject unknown top-level keys")
        record = records[schema_id]
        expected_path = f"schema/{filename}"
        if record["relativePath"] != expected_path:
            raise ContractError(f"schema {schema_id} has the wrong bound relativePath")
        actual_hash = file_hash(path)
        if record["sha256"] != actual_hash:
            raise ContractError(
                f"schema {schema_id} hash mismatch: expected {record['sha256']}, found {actual_hash}"
            )


def validate_catalog(catalog: Catalog) -> None:
    verify_schema_bindings(catalog)
    base = catalog.variants.get("current-base-v1")
    advanced = catalog.variants.get("current-advanced-v1")
    if base is None or advanced is None:
        raise ContractError("catalog must contain Current Base and Current Advanced")
    base_value = base[1]
    advanced_value = advanced[1]
    if base_value["variantRole"] != "public-conservative":
        raise ContractError("Current Base must be the conservative public variant")
    if advanced_value["variantRole"] != "first-party-advanced":
        raise ContractError("Current Advanced must be the bounded first-party variant")
    advanced_only = set(advanced_value["advancedOnlyCapabilities"])
    if not advanced_only:
        raise ContractError("Current Advanced must explicitly identify its advanced-only effects")
    if not advanced_only <= set(base_value["forbiddenCapabilities"]):
        raise ContractError("Current Base must explicitly forbid every Advanced-only effect")
    if advanced_only & set(base_value["requiredCapabilities"]):
        raise ContractError("Current Base requires an Advanced-only effect")
    if base_value["releaseStatus"] in (
        "artifact-candidate", "release-candidate", "released"
    ):
        base_spec = catalog.bundle_specs["current-base-v1"][1]
        required_roles = {
            "server-runtime", "server-plugins", "client-runtime",
            "runtime-profile", "server-client-pairing", "build-provenance",
            "source-build-tool", "candidate-pairing-verifier",
        }
        roles = {artifact["role"] for artifact in base_spec["artifacts"]}
        missing_roles = sorted(required_roles - roles)
        if missing_roles:
            raise ContractError(
                "candidate Current Base lacks artifact roles: "
                + ", ".join(missing_roles)
            )
        required_scenarios = {
            "base-artifact-public-plugin-inventory-v1",
            "base-artifact-public-state-policy-v1",
            "base-artifact-advanced-exclusion-v1",
            "base-artifact-server-client-pairing-v1",
            "base-canonical-map-bootstrap-v1",
        }
        if not required_scenarios <= set(base_spec["requiredExecutableScenarios"]):
            raise ContractError("candidate Current Base lacks executable scenarios")


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-root", type=Path, default=DEFAULT_CATALOG)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate schemas and catalog contracts")
    resolve = subparsers.add_parser("resolve", help="resolve and hash a composition")
    resolve.add_argument("--variant", required=True)
    resolve.add_argument("--module", action="append", default=[])
    resolve.add_argument("--payload-root", type=Path, default=ROOT)
    resolve.add_argument("--output", type=Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(sys.argv[1:] if arguments is None else arguments)
    try:
        catalog = Catalog(options.catalog_root)
        validate_catalog(catalog)
        if options.command == "validate":
            result = {
                "catalogRoot": os.fspath(catalog.root),
                "platformReleaseId": catalog.platform["platformReleaseId"],
                "status": "valid",
                "variants": sorted(catalog.variants),
            }
        else:
            result = resolve_composition(
                catalog, options.variant, options.module, options.payload_root
            )
        output = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if getattr(options, "output", None):
            options.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 0
    except ContractError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

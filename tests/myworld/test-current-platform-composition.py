#!/usr/bin/env python3
"""Contract tests for current platform variants, modules, and bundle identity."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import warnings
import zipfile

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/myworld/fixtures/current-platform-composition-v1"
TOOL_PATH = ROOT / "scripts/current-platform-composition.py"
SPEC = importlib.util.spec_from_file_location("current_platform_composition", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
COMPOSITION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPOSITION)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CurrentPlatformCompositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = json.loads((FIXTURE / "scenarios.json").read_text())
        cls.scenario_by_id = {
            module["moduleId"]: module for module in cls.scenarios["modules"]
        }

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="current-platform-fixture-")
        self.payload_root = Path(self.temp.name)
        shutil.copytree(ROOT / "current-platform", self.payload_root / "current-platform")
        (self.payload_root / "scripts").mkdir()
        for script in (
            "current-platform-composition.py",
            "build-current-base.py",
            "verify-current-base.py",
        ):
            shutil.copy2(ROOT / "scripts" / script, self.payload_root / "scripts" / script)
        shutil.copytree(FIXTURE / "payload", self.payload_root / "payload")
        self.catalog_root = self.payload_root / "current-platform"
        (self.catalog_root / "modules").mkdir()
        for bundle_path in sorted((self.catalog_root / "bundle-specs").glob("*.json")):
            bundle = json.loads(bundle_path.read_text())
            for artifact in bundle["artifacts"]:
                source = self.payload_root / artifact["sourcePath"]
                if not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_bytes(
                        ("sealed synthetic bundle artifact: " + artifact["role"] + "\n").encode()
                    )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_archive(self, name: str, fixture_key: str) -> None:
        entries = json.loads((FIXTURE / "archive-entries.json").read_text())[fixture_key]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.payload_root / "payload" / name, "w") as archive:
                for entry in entries:
                    archive.writestr(entry, b"sealed synthetic class payload\n")

    def add_module(self, module_id: str, archive_fixture: str | None = None) -> None:
        scenario = self.scenario_by_id[module_id]
        code_module = scenario["kind"] == "code-plugin"
        coordinated = scenario["kind"] == "coordinated-server-client"
        if module_id == "fixture-foundation":
            source_path = "payload/fixture-foundation.jar"
            self.write_archive("fixture-foundation.jar", "safe")
        elif module_id == "fixture-shadow":
            source_path = "payload/fixture-shadow.jar"
            self.write_archive("fixture-shadow.jar", archive_fixture or "shadow")
        else:
            source_path = f"payload/{module_id}.txt"
        namespace_id = module_id.replace("-", "_")
        module = {
            "schemaId": "current-module-v1",
            "manifestType": "current-platform-module",
            "moduleId": module_id,
            "moduleVersion": scenario["moduleVersion"],
            "kind": scenario["kind"],
            "platformReleaseId": "rsc-current-platform-r1",
            "platformApiVersion": "current-extension-api-v1",
            "providesCapabilities": [f"{module_id}-capability-v1"],
            "requires": scenario["requires"],
            "conflicts": scenario["conflicts"],
            "loadAfter": scenario["loadAfter"],
            "loadBefore": scenario["loadBefore"],
            "entryPoints": (
                [f"org.rscworld.modules.{namespace_id}.Module"] if code_module else []
            ),
            "configurationNamespaces": [f"{module_id}.settings"],
            "stateMigrations": [],
            "clientPairing": {
                "required": coordinated,
                "clientCapabilityId": (
                    f"{module_id}-client-v1" if coordinated else None
                ),
            },
            "artifacts": [
                {
                    "sourcePath": source_path,
                    "bundlePath": f"modules/{module_id}/payload/{Path(source_path).name}",
                    "role": "module-payload",
                    "destination": f"managed-runtime/modules/{module_id}/{Path(source_path).name}",
                    "ownership": "provider",
                    "replacementPolicy": "content-addressed",
                    "rollbackPolicy": "pointer-rollback",
                    "provenance": "sealed-synthetic-fixture",
                }
            ],
            "semanticTests": [f"{module_id}-semantic-v1"],
            "provenance": {
                "kind": "sealed-synthetic-fixture",
                "redistributable": True,
            },
        }
        (self.catalog_root / "modules" / f"{module_id}.json").write_text(
            json.dumps(module, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def catalog(self):
        catalog = COMPOSITION.Catalog(self.catalog_root)
        COMPOSITION.validate_catalog(catalog)
        return catalog

    def test_sealed_synthetic_fixture_has_exact_inventory(self) -> None:
        lock = json.loads((FIXTURE / "fixture-lock.json").read_text())
        actual = []
        for path in sorted(FIXTURE.rglob("*")):
            if path.is_file() and path.name != "fixture-lock.json":
                actual.append(
                    {
                        "path": path.relative_to(FIXTURE).as_posix(),
                        "sha256": sha256(path),
                        "size": path.stat().st_size,
                    }
                )
        self.assertEqual("sealed-fixture-lock-v1", lock["schemaId"])
        self.assertEqual(lock["files"], actual)

    def test_platform_base_and_advanced_have_schema_bound_six_field_identity(self) -> None:
        catalog = self.catalog()
        base = COMPOSITION.resolve_composition(
            catalog, "current-base-v1", [], self.payload_root
        )
        advanced = COMPOSITION.resolve_composition(
            catalog, "current-advanced-v1", [], self.payload_root
        )
        identity_fields = (
            "platformReleaseId",
            "platformManifestHash",
            "variantId",
            "variantManifestHash",
            "moduleSetHash",
            "bundleInventoryHash",
        )
        self.assertTrue(all(base[field] for field in identity_fields))
        self.assertEqual(base["platformReleaseId"], advanced["platformReleaseId"])
        self.assertEqual(base["platformManifestHash"], advanced["platformManifestHash"])
        self.assertNotEqual(base["variantId"], advanced["variantId"])
        self.assertNotEqual(base["variantManifestHash"], advanced["variantManifestHash"])
        self.assertFalse(base["installable"])
        self.assertFalse(advanced["installable"])

    def test_schema_files_are_deeply_closed_contracts(self) -> None:
        for path in sorted((ROOT / "current-platform/schema").glob("*.schema.json")):
            schema = json.loads(path.read_text())
            pending = [("$", schema)]
            while pending:
                location, value = pending.pop()
                if isinstance(value, dict):
                    if value.get("type") == "object":
                        self.assertIs(
                            False,
                            value.get("additionalProperties"),
                            f"open object schema at {path.name}:{location}",
                        )
                        self.assertIn("required", value, f"missing required at {path.name}:{location}")
                        self.assertIn("properties", value, f"missing properties at {path.name}:{location}")
                    pending.extend((f"{location}.{key}", child) for key, child in value.items())
                elif isinstance(value, list):
                    pending.extend((f"{location}[{index}]", child) for index, child in enumerate(value))

    def test_schema_mutation_changes_transitive_composition_identity(self) -> None:
        catalog = self.catalog()
        before = COMPOSITION.resolve_composition(
            catalog, "current-base-v1", [], self.payload_root
        )
        schema_path = self.catalog_root / "schema/current-variant-v1.schema.json"
        schema_path.write_text(schema_path.read_text() + "\n", encoding="utf-8")
        platform_path = self.catalog_root / "platform/current-platform-r1.json"
        platform = json.loads(platform_path.read_text())
        for record in platform["schemaContracts"]:
            if record["schemaId"] == "current-variant-v1":
                record["sha256"] = sha256(schema_path)
        platform_path.write_text(
            json.dumps(platform, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )
        changed_catalog = self.catalog()
        after = COMPOSITION.resolve_composition(
            changed_catalog, "current-base-v1", [], self.payload_root
        )
        self.assertNotEqual(before["schemaSetHash"], after["schemaSetHash"])
        self.assertNotEqual(before["platformManifestHash"], after["platformManifestHash"])
        self.assertEqual(before["variantManifestHash"], after["variantManifestHash"])

    def test_unknown_nested_contract_field_fails_closed(self) -> None:
        variant_path = self.catalog_root / "variants/current-base-v1.json"
        variant = json.loads(variant_path.read_text())
        variant["serverClientPairing"]["unknownAuthority"] = True
        variant_path.write_text(json.dumps(variant), encoding="utf-8")
        with self.assertRaisesRegex(COMPOSITION.ContractError, "unknown unknownAuthority"):
            COMPOSITION.Catalog(self.catalog_root)

    def test_current_base_runtime_documents_validate_and_reject_nested_extensions(self) -> None:
        documents = (
            ("current-base-runtime-profile-v1.schema.json", "profile.json", "serverContent"),
            ("current-base-server-content-v1.schema.json", "server-content.json", "definitionLimits"),
        )
        runtime_root = self.catalog_root / "runtime/current-base-v1"
        schema_root = self.catalog_root / "schema"
        for schema_name, document_name, nested_key in documents:
            schema = json.loads((schema_root / schema_name).read_text())
            validator = Draft202012Validator(schema)
            document = json.loads((runtime_root / document_name).read_text())
            validator.validate(document)
            mutated = json.loads(json.dumps(document))
            mutated[nested_key]["unknownCurrentBaseField"] = True
            errors = list(validator.iter_errors(mutated))
            self.assertTrue(errors, f"{document_name} accepted an unknown nested field")
            self.assertIn("Additional properties are not allowed", errors[0].message)

    def test_base_contract_is_positive_public_and_advanced_negative(self) -> None:
        catalog = self.catalog()
        base = catalog.variants["current-base-v1"][1]
        advanced = catalog.variants["current-advanced-v1"][1]
        self.assertEqual("public-conservative", base["variantRole"])
        self.assertIn("canonical-public-gameplay-v1", base["requiredCapabilities"])
        self.assertIn("canonical-public-state-v1", base["requiredCapabilities"])
        advanced_only = set(advanced["advancedOnlyCapabilities"])
        self.assertTrue(advanced_only)
        self.assertTrue(advanced_only <= set(base["forbiddenCapabilities"]))
        self.assertTrue(advanced_only.isdisjoint(base["requiredCapabilities"]))
        base_inventory = COMPOSITION.resolve_composition(
            catalog, "current-base-v1", [], self.payload_root
        )["bundleInventory"]
        self.assertFalse(
            any("current-advanced" in artifact["bundlePath"] for artifact in base_inventory)
        )

    def test_input_adapter_is_migration_only_and_build_never_trusts_receipts(self) -> None:
        catalog = self.catalog()
        boundary = catalog.platform["inputAdapterBoundary"]
        self.assertFalse(boundary["installedInRuntime"])
        self.assertEqual("editor-migration-boundary-only", boundary["selectionAuthority"])
        for _, bundle in catalog.bundle_specs.values():
            self.assertEqual("selected-current-composition-source", bundle["buildPolicy"]["sourceAuthority"])
            self.assertEqual("build-and-verify-before-packaging", bundle["buildPolicy"]["rebuildPolicy"])
            self.assertEqual("never", bundle["buildPolicy"]["receiptAuthority"])
            paths = {artifact["sourcePath"] for artifact in bundle["artifacts"]}
            self.assertNotIn("server/core.jar", paths)
            self.assertFalse(any("installed-runtime-capability" in path for path in paths))

    def test_module_dependency_and_order_are_deterministic(self) -> None:
        for module_id in ("fixture-foundation", "fixture-addon", "fixture-feature"):
            self.add_module(module_id)
        catalog = self.catalog()
        first = COMPOSITION.resolve_modules(
            catalog, ["fixture-feature", "fixture-addon"]
        )
        second = COMPOSITION.resolve_modules(
            catalog, ["fixture-addon", "fixture-feature"]
        )
        expected = ["fixture-addon", "fixture-foundation", "fixture-feature"]
        self.assertEqual(expected, [module["moduleId"] for module in first])
        self.assertEqual(expected, [module["moduleId"] for module in second])

    def test_module_conflicts_and_order_cycles_fail_closed(self) -> None:
        for module_id in ("fixture-foundation", "fixture-feature", "fixture-conflict"):
            self.add_module(module_id)
        with self.assertRaisesRegex(COMPOSITION.ContractError, "conflicts"):
            COMPOSITION.resolve_modules(
                self.catalog(), ["fixture-feature", "fixture-conflict"]
            )
        shutil.rmtree(self.catalog_root / "modules")
        (self.catalog_root / "modules").mkdir()
        for module_id in ("fixture-cycle-a", "fixture-cycle-b"):
            self.add_module(module_id)
        with self.assertRaisesRegex(COMPOSITION.ContractError, "ordering cycle"):
            COMPOSITION.resolve_modules(
                self.catalog(), ["fixture-cycle-a", "fixture-cycle-b"]
            )

    def test_module_archive_cannot_shadow_platform_classes(self) -> None:
        self.add_module("fixture-shadow")
        with self.assertRaisesRegex(COMPOSITION.ContractError, "shadows"):
            COMPOSITION.resolve_composition(
                self.catalog(), "current-base-v1", ["fixture-shadow"], self.payload_root
            )

    def test_module_archive_rejects_duplicate_casefold_and_foreign_entries(self) -> None:
        for fixture_key, message in (
            ("duplicate", "duplicate entry"),
            ("casefold", "case-fold collision"),
            ("foreignResource", "outside its namespace"),
        ):
            shutil.rmtree(self.catalog_root / "modules")
            (self.catalog_root / "modules").mkdir()
            self.add_module("fixture-shadow", fixture_key)
            with self.assertRaisesRegex(COMPOSITION.ContractError, message):
                COMPOSITION.resolve_composition(
                    self.catalog(),
                    "current-base-v1",
                    ["fixture-shadow"],
                    self.payload_root,
                )

    def test_artifact_symlink_is_not_accepted_as_provider_payload(self) -> None:
        for module_id in ("fixture-foundation", "fixture-addon", "fixture-feature"):
            self.add_module(module_id)
        payload = self.payload_root / "payload/fixture-addon.txt"
        real_payload = self.payload_root / "payload/fixture-addon-real.txt"
        payload.rename(real_payload)
        payload.symlink_to(real_payload.name)
        with self.assertRaisesRegex(COMPOSITION.ContractError, "symbolic link"):
            COMPOSITION.resolve_composition(
                self.catalog(),
                "current-base-v1",
                ["fixture-addon", "fixture-feature"],
                self.payload_root,
            )

    def test_artifact_hashes_are_byte_exact_and_metadata_independent(self) -> None:
        for module_id in ("fixture-foundation", "fixture-addon", "fixture-feature"):
            self.add_module(module_id)
        catalog = self.catalog()
        first = COMPOSITION.resolve_composition(
            catalog,
            "current-base-v1",
            ["fixture-addon", "fixture-feature"],
            self.payload_root,
        )
        payload = self.payload_root / "payload/fixture-addon.txt"
        os.utime(payload, (1_000_000_000, 1_000_000_000))
        second = COMPOSITION.resolve_composition(
            catalog,
            "current-base-v1",
            ["fixture-feature", "fixture-addon"],
            self.payload_root,
        )
        self.assertEqual(first["bundleInventoryHash"], second["bundleInventoryHash"])
        payload.write_text("fixture-addon-payload-v2\n", encoding="utf-8")
        third = COMPOSITION.resolve_composition(
            catalog,
            "current-base-v1",
            ["fixture-addon", "fixture-feature"],
            self.payload_root,
        )
        self.assertNotEqual(first["bundleInventoryHash"], third["bundleInventoryHash"])
        self.assertNotEqual(first["moduleSetHash"], third["moduleSetHash"])


if __name__ == "__main__":
    unittest.main()

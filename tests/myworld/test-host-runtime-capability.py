#!/usr/bin/env python3
"""Bind installed host capabilities to the exact tested runtime artifacts."""

import hashlib
import json
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPABILITY = ROOT / "server/conf/world-builder/installed-runtime-capability-v3.json"
ARCHIVES = {
    "server-core": ROOT / "server/core.jar",
    "client-runtime": ROOT / "Client_Base/Open_RSC_Client.jar",
}


class HostRuntimeCapabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capability = json.loads(CAPABILITY.read_text(encoding="utf-8"))

    def assert_probes(self, probes):
        for probe in probes:
            archive_path = ARCHIVES[probe["archive"]]
            with zipfile.ZipFile(archive_path) as archive:
                value = archive.read(probe["archiveEntryPath"])
            for marker in probe["requiredClassMarkers"]:
                self.assertIn(marker.encode("ascii"), value)

    def test_capability_identity_and_login_source_alignment(self):
        capability = self.capability
        self.assertEqual(3, capability["schemaVersion"])
        self.assertEqual(
            "world-builder-host-runtime-capability-v3",
            capability["capabilityId"],
        )
        self.assertEqual(
            "rsc-world-editor-runtime-host-server-v3",
            capability["serverBuildId"],
        )
        required = capability["requiredHostCapabilities"]
        self.assertEqual(
            ["undecided-custom-client-framing-v1", "pinned-prebuilt-host-core-v1"],
            [item["capabilityId"] for item in required],
        )
        framing = required[0]
        alignment = framing["sourceAlignment"]
        self.assertEqual("project-runtime", alignment["payloadScope"])
        self.assertEqual("target-root", alignment["targetScope"])
        self.assertEqual(
            "replace-trusted-preimage-or-preserve",
            alignment["replacementPolicy"],
        )
        source = ROOT / alignment["targetRelativePath"]
        self.assertEqual(
            alignment["payloadSha256"],
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            ["8d247c4b1f3d7f2d41fb58b8c378894878dcf6375c05ed2d4d2c9c2aa03e336c"],
            alignment["acceptedBeforeSha256"],
        )
        self.assert_probes(framing["artifactProbes"])

        build = required[1]["buildIntegration"]
        self.assertEqual("server/build.xml", build["targetRelativePath"])
        self.assertEqual("compile_core", build["guardedTarget"])
        self.assertEqual(
            "conf/world-builder/installed-runtime-capability-v3.json",
            build["guardCapabilityRelativePath"],
        )
        self.assert_probes(required[1]["artifactProbes"])

    def test_every_package_encoding_has_concrete_artifact_probes(self):
        matrix = self.capability["packageEncodingCapabilities"]
        self.assertEqual([1, 2, 3, 4, 5], [item["encodingVersion"] for item in matrix])
        self.assertEqual(
            {
                1: "native-layered-terrain-wire-v1",
                2: "native-layered-terrain-wire-v2-u16",
                3: "layered-placement-runtime-v3",
                4: "layered-placement-runtime-v4",
                5: "layered-placement-runtime-v5",
            },
            {item["encodingVersion"]: item["capabilityId"] for item in matrix},
        )
        for item in matrix:
            self.assertTrue(item["encodings"])
            self.assertTrue(item["artifactProbes"])
            self.assert_probes(item["artifactProbes"])
        wide = matrix[1]
        self.assertEqual(
            {
                "raw-layered-sector-v2-u16",
                "visual-layered-sector-v2-u16",
                "structural-layered-sector-v2-u16",
            },
            set(wide["encodings"]),
        )
        self.assertEqual(
            {"server-core", "client-runtime"},
            {probe["archive"] for probe in wide["artifactProbes"]},
        )

    def test_receipt_migration_and_activation_are_unambiguous(self):
        migration = self.capability["receiptMigration"]
        self.assertEqual(
            "server/conf/world-builder/installed-runtime-capability-v3.json",
            migration["authoritativeTargetRelativePath"],
        )
        self.assertEqual(
            [
                "server/conf/world-builder/installed-runtime-capability-v1.json",
                "server/conf/world-builder/installed-runtime-capability-v2.json",
            ],
            migration["retiredTargetRelativePaths"],
        )
        self.assertTrue(migration["requiresSingleAuthoritativeReceipt"])
        activation = self.capability["activation"]
        self.assertEqual(
            "import-map-changes", activation["serverProfile"]["installedBy"]
        )
        self.assertEqual(
            "map-package-active", activation["serverProfile"]["requiredWhen"]
        )
        legacy = activation["legacyDataPolicy"]
        self.assertFalse(legacy["deletesLegacyTerrainFiles"])
        self.assertFalse(legacy["deletesLegacyPlacementFiles"])
        self.assertEqual("native-layered-package", legacy["terrainRuntimeAuthority"])
        self.assertEqual("native-layered-package", legacy["placementRuntimeAuthority"])

    def test_capabilities_are_backed_by_behavioral_tests(self):
        decoder_test = (ROOT / "tests/myworld/test-custom-login-decoder.py").read_text(
            encoding="utf-8"
        )
        for evidence in (
            "fragmentedAtEveryBoundary",
            "registrationFrame",
            "initialConfigAndLegacyTrafficRemainDistinct",
            "malformedAndTruncatedFramesFailClosed",
        ):
            self.assertIn(evidence, decoder_test)
        wide_test = (ROOT / "tests/myworld/test-wide-terrain-elevation-v2.py").read_text(
            encoding="utf-8"
        )
        for evidence in (
            "copyWireBytes",
            "visual-layered-sector-v2-u16",
            "structural-layered-sector-v2-u16",
            "65535",
        ):
            self.assertIn(evidence, wide_test)
        real_login = (
            ROOT / "tests/myworld/test-adaptive-builder-real-login.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Processed login request for Builder response: 86", real_login)


if __name__ == "__main__":
    unittest.main()

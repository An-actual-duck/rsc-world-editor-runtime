#!/usr/bin/env python3
"""Bind the installed host capability to tested source and bytecode."""

import hashlib
import json
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPABILITY = (
    ROOT / "server/conf/world-builder/installed-runtime-capability-v3.json"
)


class HostRuntimeCapabilityTest(unittest.TestCase):
    def test_login_framing_capability_matches_source_and_core(self):
        capability = json.loads(CAPABILITY.read_text(encoding="utf-8"))
        self.assertEqual(2, capability["schemaVersion"])
        self.assertEqual(
            "world-builder-host-runtime-capability-v2",
            capability["capabilityId"],
        )
        self.assertEqual(
            "rsc-world-editor-runtime-host-server-v2",
            capability["serverBuildId"],
        )
        required = capability["requiredHostCapabilities"]
        self.assertEqual(1, len(required))
        framing = required[0]
        self.assertEqual(
            "undecided-custom-client-framing-v1", framing["capabilityId"]
        )

        source_contract = framing["sourceIntegration"]
        self.assertEqual(
            "server/conf/world-builder/host-integration/RSCProtocolDecoder.java",
            source_contract["payloadRelativePath"],
        )
        source = ROOT / "server" / source_contract["targetRelativePath"].removeprefix(
            "server/"
        )
        self.assertEqual(
            source_contract["payloadSha256"],
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            ["8d247c4b1f3d7f2d41fb58b8c378894878dcf6375c05ed2d4d2c9c2aa03e336c"],
            source_contract["acceptedBeforeSha256"],
        )

        artifact = framing["artifactProbe"]
        self.assertEqual("server/core.jar", artifact["targetRelativePath"])
        with zipfile.ZipFile(ROOT / artifact["targetRelativePath"]) as archive:
            decoder = archive.read(artifact["archiveEntryPath"])
        self.assertEqual(
            artifact["payloadEntrySha256"], hashlib.sha256(decoder).hexdigest()
        )
        for symbol in artifact["requiredClassSymbols"]:
            self.assertIn(symbol.encode("ascii"), decoder)

    def test_capability_is_backed_by_production_decoder_tests(self):
        decoder_test = (
            ROOT / "tests/myworld/test-custom-login-decoder.py"
        ).read_text(encoding="utf-8")
        for evidence in (
            "fragmentedAtEveryBoundary",
            "registrationFrame",
            "initialConfigAndLegacyTrafficRemainDistinct",
            "malformedAndTruncatedFramesFailClosed",
        ):
            self.assertIn(evidence, decoder_test)
        real_login = (
            ROOT / "tests/myworld/test-adaptive-builder-real-login.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Processed login request for Builder response: 86", real_login)
        self.assertIn("login response:86", real_login)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Actual packaged Base loader parity against the reviewed public data."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'output/current-platform/current-base-v1'


class PublicRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('CURRENT_BASE_PUBLIC_USE_EXISTING') != '1':
            subprocess.run(['python3', str(ROOT / 'scripts/build-current-base.py')],
                           cwd=ROOT, check=True, capture_output=True, text=True, timeout=240)

    def probe(self, role):
        with tempfile.TemporaryDirectory(prefix='current-base-public-runtime-') as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(OUTPUT / role / 'content.zip') as archive:
                archive.extractall(root)
            jars = [OUTPUT / role / ('core.jar' if role == 'server' else 'Open_RSC_Client.jar')]
            if role == 'server':
                plugins = OUTPUT / 'server/plugins.jar'
                (root / 'plugins.jar').write_bytes(plugins.read_bytes())
                jars.append(plugins)
            classpath = os.pathsep.join(map(str, jars))
            subprocess.run(['javac', '-cp', classpath, '-d', str(root),
                str(ROOT / 'tests/myworld/fixtures/current-base-public/PublicDefinitionProbe.java')],
                cwd=root, check=True, capture_output=True, text=True, timeout=30)
            command = ['java', '-Djava.awt.headless=true',
                '-Dopenrsc.currentCompositionIdentityFile=' + str(OUTPUT / 'composition-identity.json'),
                '-cp', str(root) + os.pathsep + classpath, 'PublicDefinitionProbe', role,
                str(ROOT / 'current-platform/runtime/current-base-v1/public-definitions')]
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout[-6000:] + result.stderr[-12000:])
            self.assertIn('PUBLIC_DEFINITIONS_VERIFIED role=' + role, result.stdout)

    def test_actual_public_server_definitions(self):
        self.probe('server')

    def test_actual_public_client_definitions(self):
        self.probe('client')


if __name__ == '__main__':
    unittest.main()

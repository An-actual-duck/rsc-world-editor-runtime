#!/usr/bin/env python3
"""Actual Floor controls, palette pixels, wire payload, and inspected-copy intent."""
from pathlib import Path
import bz2
import importlib.util
import os
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('floor',ROOT/'scripts/standard-floors.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='friendly-floor-ui-') as tmp:
    output=Path(tmp)
    screenshots=Path(os.environ.get('FRIENDLY_FLOOR_SCREENSHOTS',tmp))
    screenshots.mkdir(parents=True,exist_ok=True)
    definitions=output/'TileDef.xml';definitions.write_bytes(module.transform((ROOT/'current-platform/runtime/current-base-v1/public-definitions/TileDef.xml').read_bytes()))
    archive=(ROOT/'Client_Base/Cache/video/library.orsc').read_bytes()
    fonts=output/'fonts.bin';fonts.write_bytes(bz2.decompress(b'BZh1'+archive[6:]))
    jar=ROOT/'Client_Base/Open_RSC_Client.jar'
    subprocess.run(['javac','-cp',str(jar),'-d',tmp,str(ROOT/'tests/myworld/fixtures/friendly-floor/FriendlyFloorUiProbe.java')],check=True)
    subprocess.run(['java','-Djava.awt.headless=true','-cp',tmp+':'+str(jar),'com.openrsc.interfaces.misc.FriendlyFloorUiProbe',str(definitions),str(fonts),str(screenshots),str(ROOT/"current-platform/runtime/current-base-v1/public-definitions/TileDef.xml")],check=True,cwd=ROOT)

#!/usr/bin/env python3
"""Launch the built adaptive server and desktop client through real login."""

import hashlib
import json
import os
import copy
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"
PLUGINS = ROOT / "server/plugins.jar"
CLIENT = ROOT / "Client_Base/Open_RSC_Client.jar"
PRODUCTION_DEFINITION_COUNTS = {
    "boundaries": 214,
    "scenery": 1332,
    "npcs": 845,
    "groundItems": 3309,
    "tiles": 26,
}

CONTENT_SPECS = (
    ("asset.sprite.authentic", "client/Cache/video/Authentic_Sprites.orsc", "application/vnd.openrsc.archive", False),
    ("asset.sprite.custom", "client/Cache/video/Custom_Sprites.osar", "application/gzip", False),
    ("asset.library", "client/Cache/video/library.orsc", "application/vnd.openrsc.archive", False),
    ("asset.model", "client/Cache/video/models.orsc", "application/vnd.openrsc.archive", False),
    ("asset.spritepack", "client/Cache/video/spritepacks/Menus.osar", "application/gzip", False),
    ("definition.boundary", "server/conf/server/defs/DoorDef.xml", "application/xml", True),
    ("definition.scenery", "server/conf/server/defs/GameObjectDef.xml", "application/xml", True),
    ("definition.item.base", "server/conf/server/defs/ItemDefs.json", "application/json", True),
    ("definition.item.custom", "server/conf/server/defs/ItemDefsCustom.json", "application/json", True),
    ("definition.item.patch", "server/conf/server/defs/ItemDefsPatch18.json", "application/json", True),
    ("definition.item.world", "server/conf/server/defs/ItemDefsMyWorld.json", "application/json", True),
    ("definition.npc.base", "server/conf/server/defs/NpcDefs.json", "application/json", True),
    ("definition.npc.custom", "server/conf/server/defs/NpcDefsCustom.json", "application/json", True),
    ("definition.npc.patch", "server/conf/server/defs/NpcDefsPatch18.json", "application/json", True),
    ("definition.npc.world", "server/conf/server/defs/NpcDefsMyWorld.json", "application/json", True),
    ("definition.tile", "server/conf/server/defs/TileDef.xml", "application/xml", True),
)


def canonical_json(value) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_sorted(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def project_content_family_bindings():
    return [
        {"family": "floor", "definitionRoles": ["definition.tile"], "assetRoles": ["asset.sprite.custom"]},
        {"family": "ground-item", "definitionRoles": ["definition.item.base", "definition.item.custom", "definition.item.patch", "definition.item.world"], "assetRoles": ["asset.library", "asset.sprite.authentic", "asset.sprite.custom", "asset.spritepack"]},
        {"family": "npc", "definitionRoles": ["definition.npc.base", "definition.npc.custom", "definition.npc.patch", "definition.npc.world"], "assetRoles": ["asset.library", "asset.sprite.authentic", "asset.sprite.custom", "asset.spritepack"]},
        {"family": "scenery", "definitionRoles": ["definition.scenery"], "assetRoles": ["asset.library", "asset.model", "asset.sprite.custom"]},
        {"family": "wall", "definitionRoles": ["definition.boundary"], "assetRoles": ["asset.sprite.custom"]},
    ]


def write_real_project_content_bundle(bundle: Path, server_root: Path,
                                      client_root: Path):
    payloads = {}
    for role, runtime_path, _, _ in CONTENT_SPECS:
        source = (server_root / runtime_path.removeprefix("server/")) if runtime_path.startswith("server/") else (client_root / runtime_path.removeprefix("client/"))
        payloads[runtime_path] = source.read_bytes()

    for runtime_path, target_count, name in (
        ("server/conf/server/defs/TileDef.xml", 32, "fixture-floor"),
        ("server/conf/server/defs/DoorDef.xml", 220, "fixture-wall"),
        ("server/conf/server/defs/GameObjectDef.xml", 1333, "fixture-scenery"),
    ):
        root = ET.fromstring(payloads[runtime_path])
        while len(root) < target_count:
            row = copy.deepcopy(root[-1])
            name_node = row.find("name")
            if name_node is not None:
                name_node.text = f"{name}-{len(root)}"
            root.append(row)
        payloads[runtime_path] = ET.tostring(root, encoding="utf-8") + b"\n"

    npc_path = "server/conf/server/defs/NpcDefsCustom.json"
    npc_document = json.loads(payloads[npc_path])
    for npc_id in (845, 846):
        row = copy.deepcopy(npc_document["npcs"][-1])
        row["id"] = npc_id
        row["name"] = f"Project content NPC {npc_id}"
        npc_document["npcs"].append(row)
    payloads[npc_path] = (json.dumps(npc_document, indent=4) + "\n").encode()

    item_path = "server/conf/server/defs/ItemDefsCustom.json"
    item_document = json.loads(payloads[item_path])
    item = copy.deepcopy(item_document["items"][-1])
    item["id"] = 9000
    item["name"] = "Project content item 9000"
    item_document["items"].append(item)
    payloads[item_path] = (json.dumps(item_document, indent=4) + "\n").encode()

    catalog = {
        "schemaVersion": 1,
        "manifestType": "world-builder-definition-catalog",
        "catalogId": "target-adopted-content-v1",
        "tiles": list(range(32)),
        "boundaries": list(range(220)),
        "scenery": list(range(1333)),
        "npcs": list(range(847)),
        "groundItems": list(range(3309)) + [9000],
        "catalogSha256": "0" * 64,
    }
    catalog["catalogSha256"] = hashlib.sha256(canonical_sorted(catalog)).hexdigest()
    records = []
    for role, runtime_path, media, definition in sorted(CONTENT_SPECS, key=lambda row: row[1]):
        payload = payloads[runtime_path]
        destination = bundle / "files" / runtime_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        records.append({"role": role, "bundleRelativePath": "files/" + runtime_path,
                        "runtimeRelativePath": runtime_path, "mediaType": media,
                        "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})

    definition_roles = {role for role, _, _, definition in CONTENT_SPECS if definition}
    def domain_fingerprint(domain, definition):
        digest = hashlib.sha256(domain)
        for row in records:
            if (row["role"] in definition_roles) != definition:
                continue
            digest.update(f'{row["role"]}\0{row["runtimeRelativePath"]}\0{row["size"]}\0{row["sha256"]}\n'.encode())
        if definition:
            digest.update(catalog["catalogSha256"].encode())
        return digest.hexdigest()

    manifest = {
        "schemaVersion": 1,
        "manifestType": "world-builder-project-content-bundle",
        "capabilityId": "project-local-custom-content-v1",
        "sourceKind": "target-adopted",
        "definitionCatalog": catalog,
        "familyBindings": project_content_family_bindings(),
        "files": records,
        "definitionFingerprintSha256": domain_fingerprint(b"world-builder-project-content-definitions-v1\n", True),
        "assetFingerprintSha256": domain_fingerprint(b"world-builder-project-content-assets-v1\n", False),
        "bundleFingerprintSha256": "0" * 64,
    }
    manifest["bundleFingerprintSha256"] = hashlib.sha256(
        b"world-builder-project-content-bundle-v1\n" + canonical_sorted(manifest)
    ).hexdigest()
    (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    authoring = dict(catalog)
    del authoring["catalogSha256"]
    return manifest, authoring


def write_integration_package(root: Path, *, project_origin: str) -> None:
    if project_origin == "target-packed":
        write_packed_conversion_package(root)
        return
    seeded = project_origin == "target-layered"
    initial_x = 120
    initial_y = 648
    sector_x = initial_x // 48
    sector_y = initial_y // 48
    local_x = initial_x % 48
    local_y = initial_y % 48
    terrain_path = f"terrain/global/lp0/xp{sector_x}-yp{sector_y}.raw"
    placement_path = "placements/global/lp0.json"
    terrain = bytearray(
        bytes((0, 1, 8, 0, 0, 0, 0, 0, 0, 0)) * (48 * 48)
    )
    for x in range(local_x - 1, local_x + 2):
        for y in range(local_y - 1, local_y + 2):
            offset = (x * 48 + y) * 10
            terrain[offset:offset + 10] = bytes(10)
    terrain = bytes(terrain)
    placement_document = {
        "schemaVersion": 3,
        "encoding": "layered-world-placements-v3",
        "worldSpace": "global",
        "level": 0,
        "npcs": [],
        "groundItems": [],
        "scenery": [],
        "boundaries": [],
    }
    if seeded:
        placement_document.update({
            "npcs": [{
                "placementId": "integration.seed.npc",
                "npcId": 0,
                "start": {"x": 130, "y": 630},
                "roamBounds": {
                    "minimum": {"x": 130, "y": 630},
                    "maximum": {"x": 130, "y": 630},
                },
            }],
            "groundItems": [{
                "placementId": "integration.seed.item",
                "itemId": 10,
                "position": {"x": 131, "y": 630},
                "amount": 1,
                "respawnSeconds": 30,
            }],
            "scenery": [{
                "placementId": "integration.seed.scenery",
                "sceneryId": 0,
                "position": {"x": 132, "y": 630},
                "direction": 0,
            }],
            "boundaries": [{
                "placementId": "integration.seed.boundary",
                "boundaryId": 0,
                "position": {"x": 133, "y": 630},
                "direction": 0,
            }, {
                # Reproduce an appended lower-coordinate placement in an
                # already nonempty adopted package.
                "placementId": "zz.integration.lower.boundary",
                "boundaryId": 1,
                "position": {"x": 125, "y": 630},
                "direction": 2,
            }],
        })
    placements = canonical_json(placement_document)
    (root / terrain_path).parent.mkdir(parents=True)
    (root / placement_path).parent.mkdir(parents=True)
    (root / terrain_path).write_bytes(terrain)
    (root / placement_path).write_bytes(placements)
    manifest = {
        "schemaVersion": 1,
        "packageType": "layered-world",
        "packageId": (
            "integration.neutral.target-layered"
            if seeded else "integration.neutral.standalone-empty"
        ),
        "packageVersion": "1.0.0",
        "coordinateModel": "signed-layered-v1",
        "storage": {"sectorSize": 48, "presentationChunkSize": 24},
        "worldSpaces": [{"id": "global", "kind": "static"}],
        "levels": [{
            "worldSpace": "global", "level": 0,
            "name": "Bound project level", "role": "authoring-level",
        }],
        "terrainSectors": [{
            "worldSpace": "global", "level": 0,
            "sectorX": sector_x, "sectorY": sector_y,
            "encoding": "raw-layered-sector-v1", "path": terrain_path,
            "sha256": hashlib.sha256(terrain).hexdigest(),
        }],
        "placementSets": [{
            "id": "integration.global.lp0", "worldSpace": "global", "level": 0,
            "encoding": "layered-world-placements-v3", "path": placement_path,
            "sha256": hashlib.sha256(placements).hexdigest(),
        }],
    }
    (root / "manifest.json").write_bytes(canonical_json(manifest))


def write_packed_conversion_package(root: Path) -> None:
    """Mirror the converted-package shape that exposed the global-edge bug."""
    placement_documents = {
        -1: {
            "boundaries": [],
            "groundItems": [],
            "npcs": [],
            "scenery": [{
                "direction": 6,
                "placementId": (
                    "p-8f23c848e0b8b2c2076423ca7cd7696d5b2d2042a41345e5853562cf7203bafa"
                ),
                "position": {"x": 1, "y": 943},
                "sceneryId": 21,
            }],
        },
        0: {
            "boundaries": [{
                "boundaryId": 10,
                "direction": 0,
                "placementId": (
                    "p-80318ad49fd89f23e802d00a5c7f6586e3aa1677ad8bbda8e847621da041cb1b"
                ),
                "position": {"x": 0, "y": 0},
            }, {
                "boundaryId": 11,
                "direction": 2,
                "placementId": (
                    "p-e1c30d9445e8e664a898554b52b4154f2c2ddeabe1cdf585fefe19f0ad983f57"
                ),
                "position": {"x": 9, "y": 9},
            }],
            "groundItems": [],
            "npcs": [],
            "scenery": [],
        },
        1: {
            "boundaries": [],
            "groundItems": [],
            "npcs": [{
                "npcId": 30,
                "placementId": (
                    "p-5268479e269a7fb07c5f4467dbf7fcb7d7083a6e64d842bddacb714d243ebed3"
                ),
                "roamBounds": {
                    "maximum": {"x": 5, "y": 5},
                    "minimum": {"x": 1, "y": 1},
                },
                "start": {"x": 3, "y": 3},
            }],
            "scenery": [],
        },
        2: {
            "boundaries": [],
            "groundItems": [{
                "amount": 3,
                "itemId": 41,
                "placementId": (
                    "p-d46b5254441e49f93c7842a3aa3927f4033abdd252f0cf380400ff132d30dae0"
                ),
                "position": {"x": 32767, "y": 0},
                "respawnSeconds": 90,
            }],
            "npcs": [],
            "scenery": [],
        },
    }
    placement_sets = []
    for level, families in placement_documents.items():
        level_name = f"lm{-level}" if level < 0 else f"lp{level}"
        path = f"placements/global/{level_name}.json"
        document = {
            "schemaVersion": 3,
            "encoding": "layered-world-placements-v3",
            "worldSpace": "global",
            "level": level,
            **families,
        }
        payload = canonical_json(document)
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(payload)
        placement_sets.append({
            "id": f"global-{level_name}",
            "worldSpace": "global",
            "level": level,
            "encoding": "layered-world-placements-v3",
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
        })

    terrain_specs = [
        (-1, 0, 0),
        (-1, 0, 19),
        (0, 0, 0),
        (0, 2, 13),  # Dedicated visible authoring area for the built client probe.
        (1, 0, 0),
        (2, 682, 0),
    ]
    terrain_sectors = []
    for level, sector_x, sector_y in terrain_specs:
        terrain = bytearray(
            bytes((0, 1, 8, 0, 0, 0, 0, 0, 0, 0)) * (48 * 48)
        )
        if level == 0 and sector_x == 2 and sector_y == 13:
            for x in range(23, 26):
                for y in range(23, 26):
                    offset = (x * 48 + y) * 10
                    terrain[offset:offset + 10] = bytes(10)
        terrain = bytes(terrain)
        level_name = f"lm{-level}" if level < 0 else f"lp{level}"
        path = f"terrain/global/{level_name}/xp{sector_x}-yp{sector_y}.raw"
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(terrain)
        terrain_sectors.append({
            "worldSpace": "global",
            "level": level,
            "sectorX": sector_x,
            "sectorY": sector_y,
            "encoding": "raw-layered-sector-v1",
            "path": path,
            "sha256": hashlib.sha256(terrain).hexdigest(),
        })

    manifest = {
        "schemaVersion": 1,
        "packageType": "layered-world",
        "packageId": (
            "world-builder.converted."
            "43cd84e2795c28bf3a570aa5b523763c6e70fc099e724143dfb3e517fc2f332e"
        ),
        "packageVersion": "1.0.0",
        "coordinateModel": "signed-layered-v1",
        "storage": {"sectorSize": 48, "presentationChunkSize": 24},
        "worldSpaces": [{"id": "global", "kind": "static"}],
        "levels": [{
            "worldSpace": "global",
            "level": level,
            "name": f"Level {level}",
            "role": f"level-{'m' + str(-level) if level < 0 else 'p' + str(level)}",
        } for level in (-1, 0, 1, 2)],
        "terrainSectors": terrain_sectors,
        "placementSets": placement_sets,
    }
    (root / "manifest.json").write_bytes(canonical_json(manifest))


def inventory_fingerprint(package: Path, classes: Path) -> str:
    source = classes / "PackageFingerprint.java"
    source.write_text(
        """
import com.openrsc.server.io.AdaptiveWorldBuilderPackageGuard;
import java.nio.file.Paths;
public final class PackageFingerprint {
  public static void main(String[] args) throws Exception {
    System.out.println(AdaptiveWorldBuilderPackageGuard
      .requireClosedPackage(Paths.get(args[0])).getFingerprint());
  }
}
""".strip() + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
         "-d", str(classes), str(source)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        ["java", "-cp", os.pathsep.join((str(CORE), str(classes))),
         "PackageFingerprint", str(package)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    value = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise AssertionError("invalid package fingerprint: " + value)
    return value


def verify_packed_edge_ownership_contract(package: Path, classes: Path) -> None:
    source = classes / "PackedEdgeOwnership.java"
    source.write_text(
        r"""
import com.openrsc.server.constants.Constants;
import com.openrsc.server.event.rsc.GameTickEventRestorationCollisionFootprintPlanner;
import com.openrsc.server.event.rsc.GameTickEventRestorationCollisionFootprintPlanner.ConstructorState;
import com.openrsc.server.event.rsc.GameTickEventRestorationCollisionFootprintPlanner.Definition;
import com.openrsc.server.event.rsc.GameTickEventRestorationCollisionFootprintPlanner.Operation;
import com.openrsc.server.event.rsc.GameTickEventRestorationCollisionFootprintPlanner.Result;
import com.openrsc.server.event.rsc.GameTickEventRestorationCollisionFootprintPlanner.WorldBounds;
import com.openrsc.server.event.rsc.GameTickEventRestorationTransientRollbackSnapshot.CollisionContribution;
import com.openrsc.server.io.NativeLayeredWorldPackage;
import com.openrsc.server.io.NativeLayeredWorldPackageCatalog;
import com.openrsc.server.model.world.NativeLayeredGameObjectRegistry;
import com.openrsc.server.model.world.coordinate.WorldCoordinate;
import com.openrsc.server.model.world.coordinate.WorldLocation;
import com.openrsc.server.model.world.coordinate.WorldSpaceId;
import java.nio.file.Paths;
import java.util.Collections;

public final class PackedEdgeOwnership {
  public static void main(String[] args) throws Exception {
    NativeLayeredWorldPackage worldPackage =
      NativeLayeredWorldPackage.load(Paths.get(args[0]));
    NativeLayeredWorldPackageCatalog catalog =
      NativeLayeredWorldPackageCatalog.of(Collections.singleton(worldPackage));
    Definition boundary = Definition.boundary(1, "Boundary", new String[0]);
    WorldBounds bounds = WorldBounds.of(Constants.MAX_WIDTH, Constants.MAX_HEIGHT);

    Result globalEdge = GameTickEventRestorationCollisionFootprintPlanner
      .planClippedToWorld(
        Operation.REGISTER, ConstructorState.of(10, 0, 0, 0, 1),
        boundary, false, bounds);
    check(globalEdge.isFootprintAvailable()
        && globalEdge.getContributionTileCount() == 1,
      "global edge clips only the out-of-world reciprocal effect");
    WorldLocation edgeAnchor = location(0, 0);
    requireOwned(catalog, worldPackage, globalEdge);

    NativeLayeredGameObjectRegistry<Object> registry =
      new NativeLayeredGameObjectRegistry<Object>();
    Object placed = new Object();
    long generation = registry.getGeneration();
    check(registry.register(
        generation, "packed-edge", edgeAnchor, 1, 0, placed,
        globalEdge, Collections.<WorldLocation>emptyList()) == placed,
      "global-edge collision registers");
    check(registry.getCollisionTileCount() == 1,
      "global-edge collision retains one in-world tile");
    check(registry.unregister(generation, "packed-edge", placed) == placed
        && registry.getCollisionTileCount() == 0,
      "global-edge removal clears the exact clipped footprint");

    Result packageEdge = GameTickEventRestorationCollisionFootprintPlanner
      .planClippedToWorld(
        Operation.REGISTER, ConstructorState.of(10, 96, 624, 0, 1),
        boundary, false, bounds);
    check(packageEdge.isFootprintAvailable()
        && packageEdge.getContributionTileCount() == 2,
      "ordinary in-world package edge is not planner-clipped");
    try {
      requireOwned(catalog, worldPackage, packageEdge);
      throw new AssertionError("Expected uncovered package-edge refusal");
    } catch (IllegalStateException expected) {
      check(expected.getMessage().contains("uncovered package-edge"),
        "uncovered package-edge refusal reason");
    }
  }

  private static void requireOwned(
      NativeLayeredWorldPackageCatalog catalog,
      NativeLayeredWorldPackage anchorOwner,
      Result footprint) {
    for (CollisionContribution contribution : footprint.getContributions()) {
      WorldLocation tile = location(contribution.getX(), contribution.getY());
      NativeLayeredWorldPackageCatalog.requireExactTerrainOwner(
        anchorOwner, catalog.findPackage(tile).orElse(null),
        "uncovered package-edge at " + tile);
    }
  }

  private static WorldLocation location(int x, int y) {
    return new WorldLocation(
      WorldSpaceId.GLOBAL, new WorldCoordinate(x, y, 0));
  }

  private static void check(boolean condition, String label) {
    if (!condition) { throw new AssertionError(label); }
  }
}
""".strip() + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
         "-d", str(classes), str(source)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["java", "-cp", os.pathsep.join((str(CORE), str(classes))),
         "PackedEdgeOwnership", str(package)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )


def replace_config(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^(\s*{re.escape(key)}:\s*).*$")
    updated, count = pattern.subn(rf"\g<1>{value}", text, count=1)
    if count != 1:
        raise AssertionError("missing base configuration key: " + key)
    return updated


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for(path: Path, process: subprocess.Popen, timeout: float, label: str,
             diagnostic: Path = None) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        if process.poll() is not None:
            details = ""
            if diagnostic is not None and diagnostic.is_file():
                details = "\n" + diagnostic.read_text(
                    encoding="utf-8", errors="replace"
                )
            raise AssertionError(
                f"{label} process exited early with {process.returncode}{details}"
            )
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {label}: {path}")


def wait_for_text(path: Path, needle: str, process: subprocess.Popen,
                  timeout: float, label: str,
                  diagnostic: Path | None = None) -> str:
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        if path.is_file():
            latest = path.read_text(encoding="utf-8", errors="replace")
            if needle in latest:
                return latest
        if process.poll() is not None:
            if path.is_file():
                latest = path.read_text(encoding="utf-8", errors="replace")
                if needle in latest:
                    return latest
            details = ""
            if diagnostic is not None and diagnostic.is_file():
                details = "\n" + diagnostic.read_text(
                    encoding="utf-8", errors="replace"
                )
            raise AssertionError(
                f"{label} process exited early with {process.returncode}"
                f"\n{latest}{details}"
            )
        time.sleep(0.2)
    details = ""
    if diagnostic is not None and diagnostic.is_file():
        details = "\n" + diagnostic.read_text(
            encoding="utf-8", errors="replace"
        )
    raise AssertionError(
        f"timed out waiting for {label} marker {needle!r}\n{latest}{details}"
    )


def wait_for_occurrences(path: Path, needle: str, count: int,
                         process: subprocess.Popen, timeout: float,
                         label: str) -> str:
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        if path.is_file():
            latest = path.read_text(encoding="utf-8", errors="replace")
            if latest.count(needle) >= count:
                return latest
        if process.poll() is not None:
            raise AssertionError(
                f"{label} server exited early with {process.returncode}\n{latest}"
            )
        time.sleep(0.1)
    raise AssertionError(
        f"timed out waiting for {label} marker {needle!r} count {count}\n"
        + latest
    )


def recv_exact(connection: socket.socket, length: int) -> bytes:
    result = bytearray()
    while len(result) < length:
        value = connection.recv(length - len(result))
        if not value:
            raise AssertionError("config connection closed before its response frame")
        result.extend(value)
    return bytes(result)


def prove_delayed_adaptive_config_request(port: int) -> None:
    """Delay beyond the 640 ms legacy timer, then require a clean config frame."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.settimeout(0.25)
        time.sleep(0.9)
        try:
            unsolicited = connection.recv(8)
        except socket.timeout:
            unsolicited = None
        if unsolicited is not None:
            raise AssertionError(
                "adaptive config connection received unsolicited bytes: "
                + unsolicited.hex()
            )
        connection.sendall(bytes((0, 1, 19)))
        connection.settimeout(5)
        header = recv_exact(connection, 3)
        frame_length = int.from_bytes(header[:2], byteorder="big")
        if frame_length < 3 or header[2] != 19:
            raise AssertionError("corrupt adaptive config frame: " + header.hex())


def run_readiness_only_client(
    client_root: Path,
    base_properties: dict,
    runtime_log: Path,
    process_log: Path,
    label: str,
) -> tuple[str, str]:
    properties = dict(base_properties)
    properties.pop("openrsc.worldBuilderAutomatedPlacementProbe", None)
    properties.pop("openrsc.worldBuilderAutomatedDefinitionProbe", None)
    properties["openrsc.worldBuilderAutomatedExitOnReady"] = "true"
    properties["spoiledmilk.clientLog"] = str(runtime_log)
    command = ["java", "-Xms256m", "-Xmx1024m"]
    command.extend(f"-D{key}={value}" for key, value in properties.items())
    command.extend(["-jar", "Open_RSC_Client.jar"])
    with process_log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            command, cwd=client_root, stdout=output,
            stderr=subprocess.STDOUT, text=True,
        )
        try:
            runtime_evidence = wait_for_text(
                runtime_log,
                "ADAPTIVE_WORLD_BUILDER_AUTOMATED_EXIT status=0",
                process, 90, label, process_log,
            )
            if process.wait(timeout=20) != 0:
                raise AssertionError(label + " did not shut down cleanly")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    process_evidence = process_log.read_text(
        encoding="utf-8", errors="replace"
    )
    if "Fetching server configs from" not in process_evidence:
        raise AssertionError(label + " did not enter normal config startup")
    if "Got server configs!" not in process_evidence:
        raise AssertionError(label + " did not receive server configs")
    if "login response:86" not in process_evidence:
        raise AssertionError(label + " did not authenticate Builder")
    return runtime_evidence, process_evidence


def prove_bundle_v1_item_visual_contract_refusal(
    client_root: Path, base_properties: dict, process_log: Path,
) -> str:
    properties = dict(base_properties)
    properties.pop("openrsc.worldBuilderAutomatedPlacementProbe", None)
    properties.pop("openrsc.worldBuilderAutomatedDefinitionProbe", None)
    command = ["java", "-Xms256m", "-Xmx1024m"]
    command.extend(f"-D{key}={value}" for key, value in properties.items())
    command.extend(["-jar", "Open_RSC_Client.jar"])
    with process_log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            command, cwd=client_root, stdout=output,
            stderr=subprocess.STDOUT, text=True,
        )
        try:
            process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    evidence = process_log.read_text(encoding="utf-8", errors="replace")
    required = (
        "Project item 9000 has no authoritative client visual mapping; "
        "project-content-bundle-v1 cannot represent a new item visual"
    )
    if required not in evidence:
        raise AssertionError(
            "bundle-v1 client did not fail on the missing item visual contract\n"
            + evidence
        )
    if "login response:86" in evidence:
        raise AssertionError(
            "bundle-v1 client authenticated despite incomplete visual metadata"
        )
    return evidence


@unittest.skipUnless(os.environ.get("DISPLAY"), "real desktop-client integration needs DISPLAY")
class AdaptiveBuilderRealLoginTest(unittest.TestCase):
    def test_built_client_authors_saves_and_reopens_wide_elevation(self):
        for artifact in (CORE, PLUGINS, CLIENT):
            self.assertTrue(artifact.is_file(), f"build artifact missing: {artifact}")

        with tempfile.TemporaryDirectory(prefix="adaptive-real-login-") as temp:
            project_origin = os.environ.get(
                "ADAPTIVE_REAL_LOGIN_PROJECT_ORIGIN", "target-layered"
            )
            self.assertIn(
                project_origin,
                ("target-packed", "target-layered", "standalone-empty"),
            )
            seeded = project_origin != "standalone-empty"
            fixture = Path(temp)
            project = fixture / "project"
            working = project / "working"
            package = working / "layered-world/package"
            baseline = project / "source/layered-baseline/package"
            server_root = working / "runtime/server"
            client_root = working / "runtime/client"
            control = project / "run/world-builder"
            evidence = working / "evidence"
            write_integration_package(package, project_origin=project_origin)
            shutil.copytree(package, baseline)
            classes = fixture / "classes"
            classes.mkdir()
            inventory = inventory_fingerprint(package, classes)
            if project_origin == "target-packed":
                verify_packed_edge_ownership_contract(package, classes)
            manifest_sha = hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest()

            server_root.mkdir(parents=True)
            client_root.mkdir(parents=True)
            control.parent.mkdir(parents=True)
            evidence.mkdir(parents=True)
            for directory in ("conf", "database", "lib"):
                shutil.copytree(ROOT / "server" / directory, server_root / directory)
            for name in ("alertwords.txt", "badwords.txt", "goodwords.txt", "globalrules.txt"):
                shutil.copy2(ROOT / "server" / name, server_root / name)
            shutil.copy2(CORE, server_root / "core.jar")
            shutil.copy2(PLUGINS, server_root / "plugins.jar")
            (server_root / "inc/sqlite").mkdir(parents=True)
            shutil.copy2(
                ROOT / "server/inc/sqlite/myworld_seed.db",
                server_root / "inc/sqlite/world_builder.db",
            )
            shutil.copy2(ROOT / "server/connections.conf", server_root / "connections.conf")

            shutil.copy2(CLIENT, client_root / "Open_RSC_Client.jar")
            shutil.copytree(ROOT / "Client_Base/Cache", client_root / "Cache")
            for legacy in (
                client_root / "Cache/video/Authentic_Landscape.orsc",
                client_root / "Cache/video/Custom_Landscape.orsc",
            ):
                legacy.unlink()
            # Keep the unrelated Discord native integration out of this bounded
            # process-lifecycle test; the lock file is confined to the fixture.
            (client_root / "Cache/discord_inuse.txt").write_text("1", encoding="ascii")
            definitions = evidence / "adaptive-definitions.json"
            assets = evidence / "assets.bin"
            content_manifest = None
            content_bundle = working / "content-bundle"
            if project_origin == "standalone-empty":
                authoring_catalog = {
                    "schemaVersion": 1,
                    "manifestType": "world-builder-definition-catalog",
                    "catalogId": "integration.neutral.definitions.v1",
                    **{
                        family: list(range(count))
                        for family, count in PRODUCTION_DEFINITION_COUNTS.items()
                    },
                }
            else:
                content_manifest, authoring_catalog = write_real_project_content_bundle(
                    content_bundle, server_root, client_root
                )
            authorable_scenery_id = 59 if content_manifest is not None else 1
            authorable_npc_id = 846 if content_manifest is not None else 1
            authorable_item_id = 9000 if content_manifest is not None else 11
            definitions.write_text(
                json.dumps(authoring_catalog, indent=2) + "\n", encoding="utf-8"
            )
            assets.write_bytes(b"integration-neutral-asset-evidence-v1\n")
            definition_sha = hashlib.sha256(definitions.read_bytes()).hexdigest()
            asset_sha = hashlib.sha256(assets.read_bytes()).hexdigest()

            port = free_port()
            config = (ROOT / "server/myworld.conf").read_text(encoding="utf-8")
            replacements = {
                "db_name": "world_builder",
                "server_name": "Adaptive Login Integration",
                "server_name_welcome": "Adaptive Login Integration",
                "server_port": str(port),
                "ws_server_port": str(port + 1),
                "want_feature_websockets": "false",
                "max_players": "1",
                "max_players_per_ip": "1",
                "allow_in_game_world_editor": "true",
                "want_packet_register": "false",
                "want_sync_scene_baseline": "true",
                "monitor_online": "false",
                "custom_landscape": "false",
                "want_myworld": "false",
            }
            for key, value in replacements.items():
                config = replace_config(config, key, value)
            config += f"""

# Explicit isolated adaptive Builder integration profile.
world_builder_mode: true
world_builder_layered_review_mode: true
world_builder_adaptive_mode: true
want_layered_player_location_authority: true
want_layered_spatial_runtime_authority: true
want_layered_protocol_client_authority: true
want_layered_native_terrain_package: true
want_layered_native_terrain_residency: true
want_layered_native_terrain_readiness: true
want_layered_native_terrain_prediction: true
want_layered_native_terrain_symmetric_residency: true
want_layered_native_terrain_atomic_activation: true
layered_native_world_runtime_profile: adaptive-world-builder
world_builder_project_origin: {project_origin}
world_builder_definition_id: {authoring_catalog['catalogId']}
world_builder_asset_id: integration.neutral.assets.v1
world_builder_initial_world_space: global
world_builder_initial_level: 0
world_builder_initial_x: 120
world_builder_initial_y: 648
"""
            (server_root / "world-builder.conf").write_text(config, encoding="utf-8")
            runtime_root_before_start = {
                entry.name for entry in server_root.iterdir()
            }
            approved_runtime_root_additions = {
                "client.pem", "server.pem", "ipbans.txt", "logs",
            }

            credential = server_root / "inc/sqlite/world-builder.credential"
            binding = control / "runtime-binding.properties"
            ready = control / "ready"
            shutdown = control / "shutdown.request"
            server_log = fixture / "server.log"
            client_log = fixture / "client.log"
            client_runtime_log = fixture / "client-runtime.log"
            source_revision = "a" * 64
            baseline_inventory = inventory_fingerprint(baseline, classes)

            common_server_properties = {
                "openrsc.worldBuilderWorkspaceRoot": str(project),
                "openrsc.worldBuilderControlDirectory": str(control),
                "openrsc.worldBuilderCredentialFile": str(credential),
                "openrsc.worldBuilderAdaptiveMode": "true",
                "openrsc.layeredNativeWorldRuntimeProfile": "adaptive-world-builder",
                "openrsc.layeredNativeTerrainPackagePath": str(package),
                "openrsc.layeredNativeTerrainManifestSha256": manifest_sha,
                "openrsc.layeredNativeTerrainInventorySha256": inventory,
                "openrsc.worldBuilderProjectOrigin": project_origin,
                "openrsc.worldBuilderDefinitionId": authoring_catalog["catalogId"],
                "openrsc.worldBuilderDefinitionSha256": definition_sha,
                "openrsc.worldBuilderDefinitionEvidencePath": str(definitions),
                "openrsc.worldBuilderAssetId": "integration.neutral.assets.v1",
                "openrsc.worldBuilderAssetSha256": asset_sha,
                "openrsc.worldBuilderAssetEvidencePath": str(assets),
                "openrsc.worldBuilderSourceBaselineInventorySha256": baseline_inventory,
                "openrsc.worldBuilderInitialWorldSpace": "global",
                "openrsc.worldBuilderInitialLevel": "0",
                "openrsc.worldBuilderInitialX": "120",
                "openrsc.worldBuilderInitialY": "648",
            }
            if content_manifest is not None:
                common_server_properties.update({
                    "openrsc.worldBuilderContentBundle": str(content_bundle),
                    "openrsc.worldBuilderContentCapabilityId": "project-local-custom-content-v1",
                    "openrsc.worldBuilderContentBundleSha256": content_manifest["bundleFingerprintSha256"],
                    "openrsc.worldBuilderContentDefinitionSha256": content_manifest["definitionFingerprintSha256"],
                    "openrsc.worldBuilderContentAssetSha256": content_manifest["assetFingerprintSha256"],
                })
            server_command = ["java", "-Xms128m", "-Xmx768m"]
            server_command.extend(f"-D{key}={value}" for key, value in common_server_properties.items())
            server_command.extend([
                "-cp", os.pathsep.join(("lib/*", "core.jar", "plugins.jar")),
                "com.openrsc.server.Server", "world-builder.conf",
            ])

            server_output = server_log.open("w", encoding="utf-8")
            client_output = None
            server = subprocess.Popen(
                server_command, cwd=server_root, stdout=server_output,
                stderr=subprocess.STDOUT, text=True,
            )
            client = None
            try:
                wait_for(ready, server, 45, "server readiness", server_log)
                wait_for(credential, server, 5, "generated credential", server_log)
                wait_for(binding, server, 5, "runtime binding", server_log)
                prove_delayed_adaptive_config_request(port)
                self.assertEqual(20, len(credential.read_text(encoding="ascii")))
                binding_fields = dict(
                    line.split("=", 1)
                    for line in binding.read_text(encoding="ascii").splitlines()[1:]
                )
                if project_origin == "target-packed":
                    expected_required = {
                        "requiredBoundaryIds": "10,11",
                        "requiredSceneryIds": "21",
                        "requiredNpcIds": "30",
                        "requiredItemIds": "41",
                    }
                else:
                    expected_required = {
                        "requiredBoundaryIds": "0,1" if seeded else "",
                        "requiredSceneryIds": "0" if seeded else "",
                        "requiredNpcIds": "0" if seeded else "",
                        "requiredItemIds": "10" if seeded else "",
                    }
                for key, value in expected_required.items():
                    self.assertEqual(value, binding_fields[key])
                for family, key in (
                    ("tiles", "authorableFloorIds"),
                    ("boundaries", "authorableBoundaryIds"),
                    ("scenery", "authorableSceneryIds"),
                    ("npcs", "authorableNpcIds"),
                    ("groundItems", "authorableItemIds"),
                ):
                    expected = ",".join(str(value) for value in authoring_catalog[family])
                    self.assertEqual(expected, binding_fields[key])

                client_properties = {
                    "openrsc.worldBuilderMode": "true",
                    "openrsc.worldBuilderAdaptiveMode": "true",
                    "openrsc.worldBuilderHost": "127.0.0.1",
                    "openrsc.worldBuilderPort": str(port),
                    "openrsc.worldBuilderCredentialFile": str(credential),
                    "openrsc.worldBuilderProjectName": "Integration Project",
                    "openrsc.worldBuilderSourceRevision": source_revision,
                    "openrsc.worldBuilderRuntimeBindingFile": str(binding),
                    "openrsc.worldBuilderDefinitionEvidenceFile": str(definitions),
                    "openrsc.worldBuilderAssetEvidenceFile": str(assets),
                    "spoiledmilk.clientLog": str(client_runtime_log),
                    "sun.java2d.opengl": "false",
                    "openrsc.worldBuilderAutomatedPlacementProbe": "place",
                    "openrsc.worldBuilderAutomatedWideElevationProbe": "author",
                    "openrsc.worldBuilderAutomatedDefinitionProbe": "true",
                    "openrsc.worldBuilderAutomatedDisallowedBoundaryId": str(max(authoring_catalog["boundaries"]) + 1),
                    "openrsc.worldBuilderAutomatedDisallowedSceneryId": str(max(authoring_catalog["scenery"]) + 1),
                    "openrsc.worldBuilderAutomatedDisallowedNpcId": str(max(authoring_catalog["npcs"]) + 1),
                    "openrsc.worldBuilderAutomatedDisallowedItemId": str(max(authoring_catalog["groundItems"]) + 1),
                }
                if content_manifest is not None:
                    client_properties.update({
                        "openrsc.worldBuilderContentBundle": str(content_bundle),
                        "openrsc.worldBuilderContentCapabilityId": "project-local-custom-content-v1",
                        "openrsc.worldBuilderContentBundleSha256": content_manifest["bundleFingerprintSha256"],
                        "openrsc.worldBuilderContentDefinitionSha256": content_manifest["definitionFingerprintSha256"],
                        "openrsc.worldBuilderContentAssetSha256": content_manifest["assetFingerprintSha256"],
                        "openrsc.worldBuilderAutomatedAuthorableBoundaryRaw": "220",
                        "openrsc.worldBuilderAutomatedAuthorableFloorRaw": "32",
                        "openrsc.worldBuilderAutomatedAuthorableSceneryId": "59",
                        "openrsc.worldBuilderAutomatedAuthorableNpcId": "846",
                        "openrsc.worldBuilderAutomatedAuthorableItemId": "9000",
                    })
                client_command = ["java", "-Xms256m", "-Xmx1024m"]
                client_command.extend(
                    f"-D{key}={value}" for key, value in client_properties.items()
                )
                client_command.extend(["-jar", "Open_RSC_Client.jar"])

                if content_manifest is not None:
                    blocked_evidence = prove_bundle_v1_item_visual_contract_refusal(
                        client_root, client_properties,
                        fixture / "client-bundle-v1-blocked.log",
                    )
                    self.assertIn("Got server configs!", blocked_evidence)
                    server_output.flush()
                    self.assertNotIn(
                        "Player Loaded: Builder",
                        server_log.read_text(encoding="utf-8", errors="replace"),
                    )
                    shutdown.write_text("shutdown\n", encoding="ascii")
                    self.assertEqual(
                        0, server.wait(timeout=30),
                        "server clean shutdown after bundle-v1 refusal",
                    )
                    server_output.flush()
                    refusal_server_evidence = server_log.read_text(
                        encoding="utf-8", errors="replace"
                    )
                    self.assertIn("Server unloaded", refusal_server_evidence)
                    self.assertFalse(ready.exists(), "readiness cleanup")
                    return

                cold_runtime_evidence, cold_client_evidence = (
                    run_readiness_only_client(
                        client_root,
                        client_properties,
                        fixture / "client-cold-runtime.log",
                        fixture / "client-cold.log",
                        "cold manual-startup adaptive client",
                    )
                )
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_READY nativeTerrain=true "
                    "initialRegion=true binding=true",
                    cold_runtime_evidence,
                )
                self.assertNotIn(
                    "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_", cold_runtime_evidence
                )
                self.assertNotIn("socket timeout", cold_client_evidence.lower())
                wait_for_occurrences(
                    server_log, "Unregistered Builder from player list.", 1,
                    server, 10, "cold client unregister",
                )

                client_output = client_log.open("w", encoding="utf-8")
                client = subprocess.Popen(
                    client_command, cwd=client_root, stdout=client_output,
                    stderr=subprocess.STDOUT, text=True,
                )
                runtime_evidence = wait_for_text(
                    client_runtime_log,
                    "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_SAVED status=0",
                    client, 90, "adaptive client readiness", client_log,
                )
                self.assertEqual(0, client.wait(timeout=20), "desktop client clean shutdown")
                wait_for_occurrences(
                    server_log, "Unregistered Builder from player list.", 2,
                    server, 10, "placement client unregister",
                )
                client_output.flush()
                client_evidence = client_log.read_text(
                    encoding="utf-8", errors="replace"
                )
                server_output.flush()
                server_evidence = server_log.read_text(
                    encoding="utf-8", errors="replace"
                )
                self.assertEqual(2, server_evidence.count("Player Loaded: Builder"))
                self.assertEqual(
                    2, server_evidence.count("Processed login request for Builder response: 86")
                )
                self.assertEqual(
                    2,
                    server_evidence.count(
                        "Adaptive World Builder binding accepted for authenticated player Builder"
                    ),
                )
                self.assertIn(
                    "location=WorldLocation{worldSpace=global, "
                    "coordinate=WorldCoordinate{x=120, y=648, level=0}}",
                    server_evidence,
                )
                self.assertIn("nativeTerrain=true initialRegion=true binding=true", runtime_evidence)
                for marker in (
                    "stage=1 x=124 y=648 elevation=12345",
                    "stage=3 x=124 y=648 elevation=12365",
                    "stage=5 x=124 y=648 elevation=12355",
                    "stage=7 x=125 y=648 elevation=65535",
                ):
                    self.assertIn(
                        "ADAPTIVE_WORLD_BUILDER_WIDE_ELEVATION_ACCEPTED " + marker,
                        runtime_evidence,
                    )
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_WIDE_ELEVATION_ATOMIC_REFUSED "
                    "operation=raise step=1 elevations=12355,65535 neighbor=0 "
                    "mutation=false",
                    runtime_evidence,
                )
                if content_manifest is not None:
                    self.assertIn(
                        "ADAPTIVE_WORLD_BUILDER_PROJECT_FLOOR_ACCEPTED "
                        "id=31 raw=32 x=127 y=648 runtime=true",
                        runtime_evidence,
                    )
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_VISIBLE mode=place "
                    f"scenery=0@119,648,{authorable_scenery_id}@118,648 "
                    f"npc=0@120,649,{authorable_npc_id}@120,650 "
                    f"item=10@121,648,{authorable_item_id}@121,649",
                    runtime_evidence,
                )
                self.assertIn(
                    "Layered scenery placement refused: "
                    "There is already scenery in that spot.",
                    runtime_evidence,
                )
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_DEFINITION_RESPONSE "
                    "Editor request failed: East wall "
                    + str(max(authoring_catalog["boundaries"]) + 2)
                    + " is not defined.",
                    runtime_evidence,
                )
                self.assertIn(
                    "The authenticated client cannot display item definition ID "
                    + str(max(authoring_catalog["groundItems"]) + 1)
                    + " (supported range 0.."
                    + str(max(authoring_catalog["groundItems"]))
                    + ").",
                    runtime_evidence,
                )
                for family in ("scenery", "npc", "ground-item"):
                    self.assertEqual(
                        2,
                        server_evidence.count(
                            "WORLD_BUILDER_PLACEMENT_ACCEPTED family=" + family
                        ),
                    )
                self.assertIn(
                    "WORLD_BUILDER_PLACEMENT_REFUSED family=scenery id=0 "
                    "x=119 y=648 reason=There is already scenery in that spot.",
                    server_evidence,
                )
                for command in (
                    "worldeditormode", "aobject", "cnpc",
                    "buildergrounditem", "saveworldedits",
                ):
                    self.assertIn(
                        "Development.onCommand : [[Player:0:Builder @ (120, 648)], "
                        + command,
                        server_evidence,
                    )
                self.assertNotIn("Default.onCommand", server_evidence)
                self.assertIn(
                    "Skipping legacy terrain archives for explicit adaptive World Builder profile",
                    server_evidence,
                )
                if project_origin == "target-packed":
                    self.assertIn(
                        "with 1 NPC, 1 ground-item, 1 scenery, and 2 boundary placements",
                        server_evidence,
                    )
                elif seeded:
                    self.assertIn(
                        "with 1 NPC, 1 ground-item, 1 scenery, and 2 boundary placements",
                        server_evidence,
                    )
                self.assertEqual(1, client_evidence.count("login response:86"))
                combined = (
                    server_evidence + "\n" + runtime_evidence + "\n" + client_evidence
                ).lower()
                self.assertNotIn("socket timeout", combined)
                self.assertNotIn("sockettimeoutexception", combined)
                self.assertNotIn("login retry", combined)
                self.assertNotIn("lost connection", combined)
                self.assertNotIn("legacy landscape", combined)
                self.assertNotIn("fallback", combined)
                self.assertFalse((client_root / "Cache/video/Authentic_Landscape.orsc").exists())
                self.assertFalse((client_root / "Cache/video/Custom_Landscape.orsc").exists())

                placement_document = json.loads(
                    (package / "placements/global/lp0.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertIn(
                    (0, 119, 648, 0),
                    [
                        (row["sceneryId"], row["position"]["x"],
                         row["position"]["y"], row["direction"])
                        for row in placement_document["scenery"]
                    ],
                )
                self.assertIn(
                    (authorable_scenery_id, 118, 648, 0),
                    [
                        (row["sceneryId"], row["position"]["x"],
                         row["position"]["y"], row["direction"])
                        for row in placement_document["scenery"]
                    ],
                )
                self.assertNotIn(
                    max(authoring_catalog["scenery"]) + 1,
                    [row["sceneryId"] for row in placement_document["scenery"]],
                )
                self.assertIn(
                    (0, 120, 649, 120, 649, 120, 649),
                    [
                        (row["npcId"], row["start"]["x"], row["start"]["y"],
                         row["roamBounds"]["minimum"]["x"],
                         row["roamBounds"]["minimum"]["y"],
                         row["roamBounds"]["maximum"]["x"],
                         row["roamBounds"]["maximum"]["y"])
                        for row in placement_document["npcs"]
                    ],
                )
                self.assertIn(
                    (authorable_npc_id, 120, 650),
                    [
                        (row["npcId"], row["start"]["x"], row["start"]["y"])
                        for row in placement_document["npcs"]
                    ],
                )
                self.assertNotIn(
                    max(authoring_catalog["npcs"]) + 1,
                    [row["npcId"] for row in placement_document["npcs"]],
                )
                self.assertIn(
                    (10, 1, 30, 121, 648),
                    [
                        (row["itemId"], row["amount"], row["respawnSeconds"],
                         row["position"]["x"], row["position"]["y"])
                        for row in placement_document["groundItems"]
                    ],
                )
                self.assertIn(
                    (authorable_item_id, 1, 30, 121, 649),
                    [
                        (row["itemId"], row["amount"], row["respawnSeconds"],
                         row["position"]["x"], row["position"]["y"])
                        for row in placement_document["groundItems"]
                    ],
                )
                self.assertNotIn(
                    max(authoring_catalog["groundItems"]) + 1,
                    [row["itemId"] for row in placement_document["groundItems"]],
                )
                terrain_bytes = (
                    package / "terrain/global/lp0/xp2-yp13.raw"
                ).read_bytes()
                self.assertEqual(48 * 48 * 11, len(terrain_bytes))
                terrain_manifest = json.loads(
                    (package / "manifest.json").read_text(encoding="utf-8")
                )
                authored_sector = next(
                    row for row in terrain_manifest["terrainSectors"]
                    if row["worldSpace"] == "global" and row["level"] == 0
                    and row["sectorX"] == 2 and row["sectorY"] == 13
                )
                self.assertEqual("raw-layered-sector-v2-u16", authored_sector["encoding"])

                def terrain_record(world_x, world_y):
                    offset = (
                        ((world_x % 48) * 48 + (world_y % 48)) * 11
                    )
                    return (
                        int.from_bytes(terrain_bytes[offset:offset + 2], "big"),
                        *terrain_bytes[offset + 2:offset + 7],
                        int.from_bytes(terrain_bytes[offset + 7:offset + 11], "big"),
                    )

                self.assertEqual(
                    (12355, 1, 8, 0, 0, 0, 0),
                    terrain_record(124, 648),
                )
                self.assertEqual(
                    (65535, 1, 8, 0, 0, 0, 0),
                    terrain_record(125, 648),
                )
                self.assertEqual(
                    (0, 1, 8, 0, 0, 0, 0),
                    terrain_record(126, 648),
                )
                saved_terrain_bytes = terrain_bytes
                boundary_offset = ((122 % 48) * 48 + (648 % 48)) * 11 + 6
                refused_boundary_offset = ((123 % 48) * 48 + (648 % 48)) * 11 + 6
                self.assertEqual(
                    220 if content_manifest is not None else 2,
                    terrain_bytes[boundary_offset],
                )
                self.assertEqual(0, terrain_bytes[refused_boundary_offset])
                if project_origin == "target-layered":
                    self.assertEqual(
                        [(125, 630, 2, 1), (133, 630, 0, 0)],
                        [
                            (row["position"]["x"], row["position"]["y"],
                             row["direction"], row["boundaryId"])
                            for row in placement_document["boundaries"]
                        ],
                        "lower-coordinate boundary addition was not canonical",
                    )
                    self.assertEqual(
                        [(118, 648, authorable_scenery_id),
                         (119, 648, 0), (132, 630, 0)],
                        [
                            (row["position"]["x"], row["position"]["y"],
                             row["sceneryId"])
                            for row in placement_document["scenery"]
                        ],
                        "lower-coordinate scenery additions were not canonical",
                    )
                    self.assertEqual(
                        [(120, 649, 0), (120, 650, authorable_npc_id),
                         (130, 630, 0)],
                        [
                            (row["start"]["x"], row["start"]["y"],
                             row["npcId"])
                            for row in placement_document["npcs"]
                        ],
                        "lower-coordinate NPC additions were not canonical",
                    )
                    self.assertEqual(
                        [(121, 648, 10), (121, 649, authorable_item_id),
                         (131, 630, 10)],
                        [
                            (row["position"]["x"], row["position"]["y"],
                             row["itemId"])
                            for row in placement_document["groundItems"]
                        ],
                        "lower-coordinate item additions were not canonical",
                    )
                if project_origin == "target-packed":
                    self.assertIn(
                        (10, 0, 0, 0),
                        [
                            (row["boundaryId"], row["position"]["x"],
                             row["position"]["y"], row["direction"])
                            for row in placement_document["boundaries"]
                        ],
                    )
                    self.assertEqual(
                        [21],
                        [row["sceneryId"] for row in json.loads(
                            (package / "placements/global/lm1.json").read_text(
                                encoding="utf-8"
                            )
                        )["scenery"]],
                    )
                    self.assertEqual(
                        [30],
                        [row["npcId"] for row in json.loads(
                            (package / "placements/global/lp1.json").read_text(
                                encoding="utf-8"
                            )
                        )["npcs"]],
                    )
                    self.assertEqual(
                        [41],
                        [row["itemId"] for row in json.loads(
                            (package / "placements/global/lp2.json").read_text(
                                encoding="utf-8"
                            )
                        )["groundItems"]],
                    )

                reopened_runtime_log = fixture / "client-reopened-runtime.log"
                reopened_client_log = fixture / "client-reopened.log"
                reopened_properties = dict(client_properties)
                reopened_properties["openrsc.worldBuilderAutomatedPlacementProbe"] = "verify"
                reopened_properties[
                    "openrsc.worldBuilderAutomatedWideElevationProbe"
                ] = "verify"
                reopened_properties["spoiledmilk.clientLog"] = str(
                    reopened_runtime_log
                )
                reopened_command = ["java", "-Xms256m", "-Xmx1024m"]
                reopened_command.extend(
                    f"-D{key}={value}"
                    for key, value in reopened_properties.items()
                )
                reopened_command.extend(["-jar", "Open_RSC_Client.jar"])
                with reopened_client_log.open("w", encoding="utf-8") as reopened_output:
                    reopened_client = subprocess.Popen(
                        reopened_command, cwd=client_root, stdout=reopened_output,
                        stderr=subprocess.STDOUT, text=True,
                    )
                    try:
                        reopened_evidence = wait_for_text(
                            reopened_runtime_log,
                            "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_REOPENED status=0",
                            reopened_client, 90, "reopened adaptive client",
                            reopened_client_log,
                        )
                        self.assertEqual(
                            0, reopened_client.wait(timeout=20),
                            "reopened desktop client clean shutdown",
                        )
                    finally:
                        if reopened_client.poll() is None:
                            reopened_client.terminate()
                            reopened_client.wait(timeout=10)
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_VISIBLE mode=verify "
                    f"scenery=0@119,648,{authorable_scenery_id}@118,648 "
                    f"npc=0@120,649,{authorable_npc_id}@120,650 "
                    f"item=10@121,648,{authorable_item_id}@121,649",
                    reopened_evidence,
                )
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_WIDE_ELEVATION_REOPENED "
                    "elevations=12355,65535 neighbor=0 fields=1,8,0,0,0,0 "
                    "runtime=true",
                    reopened_evidence,
                )
                if content_manifest is not None:
                    self.assertIn(
                        "ADAPTIVE_WORLD_BUILDER_PROJECT_FLOOR_REOPENED "
                        "id=31 raw=32 x=127 y=648 runtime=true",
                        reopened_evidence,
                    )

                shutdown_started = time.monotonic()
                shutdown.write_text("shutdown\n", encoding="ascii")
                self.assertEqual(0, server.wait(timeout=30), "server clean shutdown")
                shutdown_elapsed = time.monotonic() - shutdown_started
                self.assertLess(
                    shutdown_elapsed, 20,
                    f"control-channel shutdown took {shutdown_elapsed:.3f}s",
                )
                server_output.flush()
                shutdown_evidence = server_log.read_text(
                    encoding="utf-8", errors="replace"
                )
                self.assertEqual(
                    1,
                    shutdown_evidence.count(
                        "World Builder launcher requested a clean local shutdown"
                    ),
                )
                self.assertIn("Server stop requested", shutdown_evidence)
                self.assertIn("Server unloaded", shutdown_evidence)
                self.assertIn("Exiting server process", shutdown_evidence)
                self.assertNotIn("Server thread termination failed", shutdown_evidence)
                self.assertFalse(shutdown.exists(), "shutdown request cleanup")
                self.assertFalse(ready.exists(), "readiness cleanup")
                self.assertNotIn(
                    "Set int session id for", shutdown_evidence,
                    "adaptive connections must never receive unsolicited legacy IDs",
                )
                runtime_root_after_first = {
                    entry.name for entry in server_root.iterdir()
                }
                unexpected_root_entries = (
                    runtime_root_after_first
                    - runtime_root_before_start
                    - approved_runtime_root_additions
                )
                self.assertEqual(set(), unexpected_root_entries)
                self.assertFalse((server_root / "create_db.log").exists())
                self.assertFalse((server_root / "create_db_error.log").exists())
                self.assertTrue((server_root / "logs/create_db.log").is_file())
                self.assertTrue(
                    (server_root / "logs/create_db_error.log").is_file()
                )

                # Reopen the exact same project-local runtime. This exercises
                # patch logging and config/login framing without rebuilding or
                # replacing any workspace content between launches.
                if client_output is not None:
                    client_output.close()
                    client_output = None
                server_output.close()
                reopened_server_properties = dict(common_server_properties)
                reopened_server_properties[
                    "openrsc.layeredNativeTerrainManifestSha256"
                ] = hashlib.sha256(
                    (package / "manifest.json").read_bytes()
                ).hexdigest()
                reopened_server_properties[
                    "openrsc.layeredNativeTerrainInventorySha256"
                ] = inventory_fingerprint(package, classes)
                reopened_server_command = [
                    "java", "-Xms128m", "-Xmx768m",
                ]
                reopened_server_command.extend(
                    f"-D{key}={value}"
                    for key, value in reopened_server_properties.items()
                )
                reopened_server_command.extend([
                    "-cp", os.pathsep.join(("lib/*", "core.jar", "plugins.jar")),
                    "com.openrsc.server.Server", "world-builder.conf",
                ])
                second_server_log = fixture / "server-reopened.log"
                server_output = second_server_log.open("w", encoding="utf-8")
                server = subprocess.Popen(
                    reopened_server_command, cwd=server_root, stdout=server_output,
                    stderr=subprocess.STDOUT, text=True,
                )
                wait_for(
                    ready, server, 45, "reopened server readiness",
                    second_server_log,
                )
                second_client_properties = dict(client_properties)
                second_client_properties[
                    "openrsc.worldBuilderAutomatedWideElevationProbe"
                ] = "verify"
                second_runtime_evidence, second_client_evidence = (
                    run_readiness_only_client(
                        client_root,
                        second_client_properties,
                        fixture / "client-second-runtime.log",
                        fixture / "client-second.log",
                        "second-launch manual-startup adaptive client",
                    )
                )
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_READY nativeTerrain=true "
                    "initialRegion=true binding=true",
                    second_runtime_evidence,
                )
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_WIDE_ELEVATION_REOPENED "
                    "elevations=12355,65535 neighbor=0 fields=1,8,0,0,0,0 "
                    "runtime=true",
                    second_runtime_evidence,
                )
                if content_manifest is not None:
                    self.assertIn(
                        "ADAPTIVE_WORLD_BUILDER_PROJECT_FLOOR_REOPENED "
                        "id=31 raw=32 x=127 y=648 runtime=true",
                        second_runtime_evidence,
                    )
                self.assertNotIn(
                    "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_", second_runtime_evidence
                )
                self.assertNotIn("socket timeout", second_client_evidence.lower())
                shutdown.write_text("shutdown\n", encoding="ascii")
                self.assertEqual(
                    0, server.wait(timeout=30),
                    "reopened server clean shutdown",
                )
                server_output.flush()
                second_server_evidence = second_server_log.read_text(
                    encoding="utf-8", errors="replace"
                )
                self.assertIn("Sending initial configs to:", second_server_evidence)
                self.assertIn(
                    "Adaptive World Builder binding accepted for authenticated "
                    "player Builder",
                    second_server_evidence,
                )
                self.assertNotIn("Set int session id for", second_server_evidence)
                self.assertIn("Server unloaded", second_server_evidence)
                self.assertEqual(
                    saved_terrain_bytes,
                    (package / "terrain/global/lp0/xp2-yp13.raw").read_bytes(),
                    "reopened runtime changed the saved wide terrain bytes",
                )
                self.assertFalse(shutdown.exists(), "second shutdown request cleanup")
                self.assertFalse(ready.exists(), "second readiness cleanup")
                self.assertEqual(
                    runtime_root_after_first,
                    {entry.name for entry in server_root.iterdir()},
                    "second launch created an unbound runtime-root entry",
                )
                self.assertFalse((server_root / "create_db.log").exists())
                self.assertFalse((server_root / "create_db_error.log").exists())
            finally:
                if client is not None and client.poll() is None:
                    client.terminate()
                    try:
                        client.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        client.kill()
                        client.wait(timeout=10)
                if server.poll() is None:
                    try:
                        shutdown.parent.mkdir(parents=True, exist_ok=True)
                        shutdown.write_text("shutdown\n", encoding="ascii")
                        server.wait(timeout=15)
                    except (OSError, subprocess.TimeoutExpired):
                        server.terminate()
                        server.wait(timeout=10)
                if client_output is not None:
                    client_output.close()
                server_output.close()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"
INSTALLED_RUNTIME = (
    ROOT / "server/world-builder-runtime/world-builder-managed-runtime.jar"
)
CLIENT = ROOT / "Client_Base/Open_RSC_Client.jar"
EVIDENCE_WRITER = ROOT / "scripts/write-adaptive-world-builder-runtime-evidence.py"


def digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return "missing"
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        if path.is_symlink():
            digest.update(b"link\0" + os.readlink(path).encode("utf-8"))
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"directory")
    return digest.hexdigest()


def canonical_json(value) -> bytes:
    return (json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


VOID_TILE = bytes((0, 1, 8, 0, 0, 0, 0, 0, 0, 0))
VISIBLE_TILE = bytes(10)


def terrain_offset(local_x: int, local_y: int) -> int:
    return (local_x * 48 + local_y) * 10


def write_package(
    root: Path, *, empty: bool = False,
    empty_start: tuple[int, int] = (0, 0), visible_patch: bool = False,
) -> None:
    root.mkdir(parents=True)
    levels = [0] if empty else [-3, 0]
    terrain = []
    placements = []
    for level in levels:
        token = f"m{-level}" if level < 0 else f"p{level}"
        sector_x = empty_start[0] // 48 if empty else 0
        sector_y = empty_start[1] // 48 if empty else 0
        sector_x_token = f"m{-sector_x}" if sector_x < 0 else f"p{sector_x}"
        sector_y_token = f"m{-sector_y}" if sector_y < 0 else f"p{sector_y}"
        terrain_path = (
            f"terrain/global/l{token}/x{sector_x_token}-y{sector_y_token}.raw"
        )
        payload = bytearray(VOID_TILE * (48 * 48))
        if empty and visible_patch:
            local_x = empty_start[0] % 48
            local_y = empty_start[1] % 48
            if local_x < 1 or local_x > 46 or local_y < 1 or local_y > 46:
                raise ValueError("visible patch cannot cross the fixture sector edge")
            for x in range(local_x - 1, local_x + 2):
                for y in range(local_y - 1, local_y + 2):
                    offset = terrain_offset(x, y)
                    payload[offset:offset + 10] = VISIBLE_TILE
        payload = bytes(payload)
        target = root / terrain_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        terrain.append(
            {
                "worldSpace": "global",
                "level": level,
                "sectorX": sector_x,
                "sectorY": sector_y,
                "encoding": "raw-layered-sector-v1",
                "path": terrain_path,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        placement_path = f"placements/global/l{token}.json"
        document = {
            "schemaVersion": 3,
            "encoding": "layered-world-placements-v3",
            "worldSpace": "global",
            "level": level,
            "npcs": [],
            "groundItems": [],
            "scenery": [],
            "boundaries": [],
        }
        if level == 0 and not empty:
            document.update(
                {
                    "npcs": [
                        {
                            "placementId": "creator.fixture.npc",
                            "npcId": 1,
                            "start": {"x": 8, "y": 8},
                            "roamBounds": {
                                "minimum": {"x": 7, "y": 7},
                                "maximum": {"x": 9, "y": 9},
                            },
                        }
                    ],
                    "groundItems": [
                        {
                            "placementId": "creator.fixture.ground-item",
                            "itemId": 2,
                            "position": {"x": 10, "y": 10},
                            "amount": 3,
                            "respawnSeconds": 45,
                        }
                    ],
                    "scenery": [
                        {
                            "placementId": "creator.fixture.scenery",
                            "sceneryId": 4,
                            "position": {"x": 12, "y": 12},
                            "direction": 3,
                        }
                    ],
                    "boundaries": [
                        {
                            "placementId": "creator.fixture.boundary",
                            "boundaryId": 5,
                            "position": {"x": 14, "y": 14},
                            "direction": 1,
                        }
                    ],
                }
            )
        placement_bytes = canonical_json(document)
        target = root / placement_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(placement_bytes)
        placements.append(
            {
                "id": f"creator.global.l{token}",
                "worldSpace": "global",
                "level": level,
                "encoding": "layered-world-placements-v3",
                "path": placement_path,
                "sha256": hashlib.sha256(placement_bytes).hexdigest(),
            }
        )
    manifest = {
        "schemaVersion": 1,
        "packageType": "layered-world",
        "packageId": "creator.arbitrary-adopted-world" if not empty else "creator.empty-world",
        "packageVersion": "7.4.2-alpha.3" if not empty else "1.0.0",
        "coordinateModel": "signed-layered-v1",
        "storage": {"sectorSize": 48, "presentationChunkSize": 24},
        "worldSpaces": [{"id": "global", "kind": "static"}],
        "levels": [
            {
                "worldSpace": "global",
                "level": level,
                "name": "Creator level " + str(level),
                "role": f"creator-level-{'m' + str(-level) if level < 0 else 'p' + str(level)}",
            }
            for level in levels
        ],
        "terrainSectors": terrain,
        "placementSets": placements,
    }
    (root / "manifest.json").write_bytes(canonical_json(manifest))


def mutate_first_terrain(root: Path, mutation) -> None:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    declaration = manifest["terrainSectors"][0]
    terrain = root / declaration["path"]
    payload = bytearray(terrain.read_bytes())
    mutation(payload, declaration)
    terrain.write_bytes(payload)
    declaration["sha256"] = hashlib.sha256(payload).hexdigest()
    (root / "manifest.json").write_bytes(canonical_json(manifest))


def add_scenery_placement(root: Path, scenery_id: int, x: int, y: int) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declaration = manifest["placementSets"][0]
    placement_path = root / declaration["path"]
    placements = json.loads(placement_path.read_text(encoding="utf-8"))
    placements["scenery"].append({
        "placementId": "creator.saved.scenery",
        "sceneryId": scenery_id,
        "position": {"x": x, "y": y},
        "direction": 0,
    })
    placement_bytes = canonical_json(placements)
    placement_path.write_bytes(placement_bytes)
    declaration["sha256"] = hashlib.sha256(placement_bytes).hexdigest()
    manifest_path.write_bytes(canonical_json(manifest))


HARNESS = r"""
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderPackagePublisher;
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderRuntimeIdentity;
import com.openrsc.server.ServerConfiguration;
import com.openrsc.server.io.AdaptiveWorldBuilderPackageGuard;
import com.openrsc.server.io.NativeLayeredBoundaryPlacement;
import com.openrsc.server.io.NativeLayeredGroundItemPlacement;
import com.openrsc.server.io.NativeLayeredNpcPlacement;
import com.openrsc.server.io.NativeLayeredPlacementSet;
import com.openrsc.server.io.NativeLayeredSceneryPlacement;
import com.openrsc.server.io.NativeLayeredTerrainSector;
import com.openrsc.server.io.NativeLayeredWorldPackage;
import com.openrsc.server.io.NativeLayeredWorldPackageCatalog;
import com.openrsc.server.io.NativeLayeredWorldRuntimeProfile;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public final class AdaptiveWorldBuilderRuntimeHarness {
    private static String placementSetId(
        NativeLayeredWorldPackage source,
        NativeLayeredWorldPackage.LevelDeclaration level) {
        String result = null;
        for (NativeLayeredPlacementSet set : source.getPlacementSets().values()) {
            if (set.getWorldSpace().equals(level.getWorldSpace())
                && set.getLevel() == level.getLevel()) {
                if (result != null) throw new IllegalStateException("ambiguous set");
                result = set.getId();
            }
        }
        if (result == null) throw new IllegalStateException("missing set");
        return result;
    }

    private static AdaptiveWorldBuilderPackagePublisher.Draft draft(
        NativeLayeredWorldPackage source, String mode) {
        List<AdaptiveWorldBuilderPackagePublisher.Level> levels = new ArrayList<>();
        for (NativeLayeredWorldPackage.LevelDeclaration level : source.getLevelDeclarations()) {
            levels.add(new AdaptiveWorldBuilderPackagePublisher.Level(
                level.getWorldSpace().getValue(), level.getLevel(),
                level.getName(), level.getRole(), placementSetId(source, level)));
        }
        List<AdaptiveWorldBuilderPackagePublisher.Sector> sectors = new ArrayList<>();
        boolean changed = false;
        for (NativeLayeredTerrainSector sector : source.getTerrainSectors().values()) {
            byte[] bytes = sector.copyWireBytes();
            if (!changed) {
                bytes[0] = (byte)((bytes[0] + 1) & 255);
                changed = true;
            }
            sectors.add(new AdaptiveWorldBuilderPackagePublisher.Sector(
                sector.getIdentity(), bytes));
        }
        List<AdaptiveWorldBuilderPackagePublisher.Boundary> boundaries = new ArrayList<>();
        List<AdaptiveWorldBuilderPackagePublisher.Scenery> scenery = new ArrayList<>();
        List<AdaptiveWorldBuilderPackagePublisher.Npc> npcs = new ArrayList<>();
        List<AdaptiveWorldBuilderPackagePublisher.GroundItem> items = new ArrayList<>();
        for (NativeLayeredPlacementSet set : source.getPlacementSets().values()) {
            for (NativeLayeredBoundaryPlacement item : set.getBoundaries()) {
                boundaries.add(new AdaptiveWorldBuilderPackagePublisher.Boundary(
                    item.getPlacementId(), item.getBoundaryId(),
                    item.getLocation(), item.getDirection()));
            }
            for (NativeLayeredSceneryPlacement item : set.getScenery()) {
                scenery.add(new AdaptiveWorldBuilderPackagePublisher.Scenery(
                    item.getPlacementId(), item.getSceneryId(),
                    item.getLocation(), item.getDirection()));
            }
            for (NativeLayeredNpcPlacement item : set.getNpcs()) {
                npcs.add(new AdaptiveWorldBuilderPackagePublisher.Npc(
                    item.getPlacementId(), item.getNpcId(), item.getStart(),
                    item.getMinX(), item.getMinY(), item.getMaxX(), item.getMaxY(),
                    item.getRespawnSeconds()));
            }
            for (NativeLayeredGroundItemPlacement item : set.getGroundItems()) {
                items.add(new AdaptiveWorldBuilderPackagePublisher.GroundItem(
                    item.getPlacementId(), item.getItemId(), item.getLocation(),
                    item.getAmount(), item.getRespawnSeconds()));
            }
        }
        if (mode.startsWith("canonical-")) {
            boundaries.add(new AdaptiveWorldBuilderPackagePublisher.Boundary(
                "zz.lower.boundary.direction-2", 6,
                com.openrsc.server.model.world.coordinate.WorldLocation.global(
                    new com.openrsc.server.model.world.coordinate.WorldCoordinate(
                        2, 2, 0)), 2));
            boundaries.add(new AdaptiveWorldBuilderPackagePublisher.Boundary(
                "zz.lower.boundary.direction-0", 7,
                com.openrsc.server.model.world.coordinate.WorldLocation.global(
                    new com.openrsc.server.model.world.coordinate.WorldCoordinate(
                        2, 2, 0)), 0));
            scenery.add(new AdaptiveWorldBuilderPackagePublisher.Scenery(
                "zz.lower.scenery", 8,
                com.openrsc.server.model.world.coordinate.WorldLocation.global(
                    new com.openrsc.server.model.world.coordinate.WorldCoordinate(
                        3, 3, 0)), 4));
            npcs.add(new AdaptiveWorldBuilderPackagePublisher.Npc(
                "zz.lower.npc", 9,
                com.openrsc.server.model.world.coordinate.WorldLocation.global(
                    new com.openrsc.server.model.world.coordinate.WorldCoordinate(
                        4, 4, 0)), 4, 4, 4, 4, 45));
            items.add(new AdaptiveWorldBuilderPackagePublisher.GroundItem(
                "zz.lower.ground-item", 10,
                com.openrsc.server.model.world.coordinate.WorldLocation.global(
                    new com.openrsc.server.model.world.coordinate.WorldCoordinate(
                        5, 5, 0)), 1, 30));
            if ("canonical-reversed".equals(mode)) {
                java.util.Collections.reverse(boundaries);
                java.util.Collections.reverse(scenery);
                java.util.Collections.reverse(npcs);
                java.util.Collections.reverse(items);
            }
        }
        return new AdaptiveWorldBuilderPackagePublisher.Draft(
            source.getPackageId(), source.getPackageVersion(),
            source.getPresentationChunkSize(), source.getWorldSpaceKinds(),
            levels, sectors, boundaries, scenery, npcs, items);
    }

    private static Path first(Path root, String suffix) throws IOException {
        try (java.util.stream.Stream<Path> values = Files.walk(root)) {
            return values.filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(suffix)).findFirst().get();
        }
    }

    private static Path firstIn(
        Path root, String directory, String suffix) throws IOException {
        try (java.util.stream.Stream<Path> values = Files.walk(root.resolve(directory))) {
            return values.filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(suffix)).findFirst().get();
        }
    }

    private static String sha256(byte[] bytes) throws Exception {
        byte[] digest = java.security.MessageDigest.getInstance("SHA-256")
            .digest(bytes);
        StringBuilder value = new StringBuilder();
        for (byte item : digest) value.append(String.format("%02x", item & 255));
        return value.toString();
    }

    private static void replaceManifestHash(
        Path root, byte[] before, byte[] after) throws Exception {
        Path manifest = root.resolve("manifest.json");
        String document = new String(
            Files.readAllBytes(manifest), java.nio.charset.StandardCharsets.UTF_8);
        String oldHash = sha256(before);
        String newHash = sha256(after);
        String changed = document.replace(oldHash, newHash);
        if (changed.equals(document)) throw new IOException("fixture hash was not found");
        Files.write(manifest, changed.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        Path working = Paths.get(args[1]);
        if ("guard".equals(mode)) {
            AdaptiveWorldBuilderPackageGuard.requireClosedPackage(working);
            System.out.println("accepted");
            return;
        }
        if ("recover".equals(mode)) {
            AdaptiveWorldBuilderPackagePublisher.recover(working);
            System.out.println("recovered");
            return;
        }
        if ("empty-origin".equals(mode) || "adopted-origin".equals(mode)
            || "empty-working".equals(mode)) {
            boolean workingDescendant = "empty-working".equals(mode);
            NativeLayeredWorldPackage source = NativeLayeredWorldPackage.load(working);
            NativeLayeredWorldRuntimeProfile.ADAPTIVE_WORLD_BUILDER.validate(
                NativeLayeredWorldPackageCatalog.of(
                    java.util.Collections.singletonList(source)));
            NativeLayeredWorldRuntimeProfile.WORLD_BUILDER_INSTALLED.validate(
                NativeLayeredWorldPackageCatalog.of(
                    java.util.Collections.singletonList(source)));
            if (!NativeLayeredWorldRuntimeProfile.WORLD_BUILDER_INSTALLED
                    .replacesLegacyBasePopulation()
                || !NativeLayeredWorldRuntimeProfile.WORLD_BUILDER_INSTALLED
                    .skipsLegacyTerrainArchive()
                || !NativeLayeredWorldRuntimeProfile.WORLD_BUILDER_INSTALLED
                    .requiresConfiguredManifestSha256()
                || NativeLayeredWorldRuntimeProfile.WORLD_BUILDER_INSTALLED
                    .requiresConfiguredInventorySha256()) {
                throw new IllegalStateException("unsafe installed profile ownership");
            }
            NativeLayeredWorldPackage origin = workingDescendant
                ? NativeLayeredWorldPackage.load(Paths.get(args[2])) : source;
            NativeLayeredWorldRuntimeProfile.ADAPTIVE_WORLD_BUILDER.validate(
                NativeLayeredWorldPackageCatalog.of(
                    java.util.Collections.singletonList(origin)));
            AdaptiveWorldBuilderPackageGuard.Inventory inventory =
                AdaptiveWorldBuilderPackageGuard.requireClosedPackage(working);
            AdaptiveWorldBuilderPackageGuard.Inventory originInventory =
                AdaptiveWorldBuilderPackageGuard.requireClosedPackage(
                    workingDescendant ? Paths.get(args[2]) : working);
            ServerConfiguration config = new ServerConfiguration();
            config.WORLD_BUILDER_MODE = true;
            config.WORLD_BUILDER_ADAPTIVE_MODE = true;
            config.LAYERED_NATIVE_WORLD_RUNTIME_PROFILE =
                AdaptiveWorldBuilderRuntimeIdentity.PROFILE_ID;
            config.WORLD_BUILDER_PROJECT_ORIGIN =
                ("empty-origin".equals(mode) || workingDescendant)
                    ? AdaptiveWorldBuilderRuntimeIdentity.ORIGIN_EMPTY
                    : AdaptiveWorldBuilderRuntimeIdentity.ORIGIN_ADOPTED;
            config.WORLD_BUILDER_DEFINITION_ID = "creator.definitions.v1";
            config.WORLD_BUILDER_DEFINITION_SHA256 =
                "1111111111111111111111111111111111111111111111111111111111111111";
            config.WORLD_BUILDER_ASSET_ID = "creator.assets.v1";
            config.WORLD_BUILDER_ASSET_SHA256 =
                "2222222222222222222222222222222222222222222222222222222222222222";
            config.WORLD_BUILDER_SOURCE_BASELINE_INVENTORY_SHA256 =
                originInventory.getFingerprint();
            config.LAYERED_NATIVE_TERRAIN_MANIFEST_SHA256 =
                source.getManifestSha256();
            config.LAYERED_NATIVE_TERRAIN_INVENTORY_SHA256 =
                inventory.getFingerprint();
            config.WORLD_BUILDER_INITIAL_WORLD_SPACE = "global";
            config.WORLD_BUILDER_INITIAL_LEVEL = 0;
            int coordinateOffset = workingDescendant ? 1 : 0;
            config.WORLD_BUILDER_INITIAL_X = args.length > 2 + coordinateOffset
                ? Integer.parseInt(args[2 + coordinateOffset]) : 0;
            config.WORLD_BUILDER_INITIAL_Y = args.length > 3 + coordinateOffset
                ? Integer.parseInt(args[3 + coordinateOffset]) : 0;
            config.CLIENT_VERSION = AdaptiveWorldBuilderRuntimeIdentity.CLIENT_VERSION;
            AdaptiveWorldBuilderRuntimeIdentity.validateOriginPackage(config, origin);
            if (workingDescendant) {
                AdaptiveWorldBuilderRuntimeIdentity.validateWorkingPackage(
                    config, origin, source);
            }
            System.out.println("accepted-" + config.WORLD_BUILDER_PROJECT_ORIGIN);
            return;
        }
        if ("composition".equals(mode)) {
            Path destination = Paths.get(args[2]);
            NativeLayeredWorldPackage source = NativeLayeredWorldPackage.load(working);
            AdaptiveWorldBuilderPackageGuard.Inventory inventory =
                AdaptiveWorldBuilderPackageGuard.requireClosedPackage(working);
            java.lang.reflect.Method writer =
                com.openrsc.server.content.worldedit.AdaptiveWorldBuilderRuntimeSession.class
                    .getDeclaredMethod(
                        "writeComposition", Path.class,
                        NativeLayeredWorldPackage.class, String.class);
            writer.setAccessible(true);
            writer.invoke(null, destination, source, inventory.getFingerprint());
            System.out.println("composition-written");
            return;
        }
        if ("snapshot-index".equals(mode)) {
            NativeLayeredWorldPackage source = NativeLayeredWorldPackage.load(working);
            com.openrsc.server.content.worldedit.WorldEditorSessionManager manager =
                new com.openrsc.server.content.worldedit.WorldEditorSessionManager();
            java.lang.reflect.Field overlayField = manager.getClass()
                .getDeclaredField("nativeTerrainOverlay");
            overlayField.setAccessible(true);
            @SuppressWarnings("unchecked")
            java.util.Map<Object,com.openrsc.server.io.NativeLayeredTerrainTile> overlay =
                (java.util.Map<Object,com.openrsc.server.io.NativeLayeredTerrainTile>)
                    overlayField.get(manager);
            Class<?> keyType = Class.forName(
                "com.openrsc.server.content.worldedit.WorldEditorSessionManager$NativeTileKey");
            java.lang.reflect.Constructor<?> keyConstructor = keyType
                .getDeclaredConstructor(
                    com.openrsc.server.model.world.coordinate.WorldLocation.class);
            keyConstructor.setAccessible(true);
            int editCount = 0;
            for (NativeLayeredTerrainSector sector : source.getTerrainSectors().values()) {
                for (int localX = 0; localX < 48 && editCount < 4096; localX++) {
                    for (int localY = 0; localY < 48 && editCount < 4096; localY++) {
                        com.openrsc.server.model.world.coordinate.WorldMapSectorId identity =
                            sector.getIdentity();
                        com.openrsc.server.model.world.coordinate.WorldLocation location =
                            new com.openrsc.server.model.world.coordinate.WorldLocation(
                                identity.getWorldSpace(),
                                new com.openrsc.server.model.world.coordinate.WorldCoordinate(
                                    identity.getSectorX() * 48 + localX,
                                    identity.getSectorY() * 48 + localY,
                                    identity.getLevel()));
                        overlay.put(
                            keyConstructor.newInstance(location),
                            new com.openrsc.server.io.NativeLayeredTerrainTile(
                                300, 7, 9, 11, 13, 15, 17000));
                        editCount++;
                    }
                }
            }
            if (editCount != 4096 || overlay.size() != 4096) {
                throw new IllegalStateException("large snapshot fixture is incomplete");
            }
            java.lang.reflect.Method snapshot = manager.getClass()
                .getDeclaredMethod("adaptiveDraft", NativeLayeredWorldPackage.class);
            snapshot.setAccessible(true);
            long started = System.nanoTime();
            Object draft = snapshot.invoke(manager, source);
            long elapsedMillis = (System.nanoTime() - started) / 1000000L;
            java.lang.reflect.Field sectorsField = draft.getClass()
                .getDeclaredField("sectors");
            sectorsField.setAccessible(true);
            @SuppressWarnings("unchecked")
            java.util.List<Object> sectors =
                (java.util.List<Object>)sectorsField.get(draft);
            int encodedEdits = 0;
            for (Object sector : sectors) {
                java.lang.reflect.Field bytesField = sector.getClass()
                    .getDeclaredField("bytes");
                bytesField.setAccessible(true);
                byte[] bytes = (byte[])bytesField.get(sector);
                for (int offset = 0; offset < bytes.length; offset += 11) {
                    if ((bytes[offset] & 255) == 1
                        && (bytes[offset + 1] & 255) == 44
                        && (bytes[offset + 2] & 255) == 7
                        && (bytes[offset + 3] & 255) == 9) {
                        encodedEdits++;
                    }
                }
            }
            if (encodedEdits != 4096) {
                throw new IllegalStateException(
                    "indexed snapshot lost terrain edits: " + encodedEdits);
            }
            if (elapsedMillis > 10000L) {
                throw new IllegalStateException(
                    "indexed large snapshot exceeded 10 seconds: " + elapsedMillis);
            }
            System.out.println("snapshot-index-ok edits=" + encodedEdits
                + " elapsedMs=" + elapsedMillis);
            return;
        }
        Path baseline = Paths.get(args[2]);
        NativeLayeredWorldPackage source = NativeLayeredWorldPackage.load(working);
        String workingHash = AdaptiveWorldBuilderPackageGuard
            .requireClosedPackage(working).getFingerprint();
        String baselineHash = AdaptiveWorldBuilderPackageGuard
            .requireClosedPackage(baseline).getFingerprint();
        AdaptiveWorldBuilderPackagePublisher.Observer observer =
            AdaptiveWorldBuilderPackagePublisher.NO_OBSERVER;
        if (!"publish".equals(mode)) {
            observer = new AdaptiveWorldBuilderPackagePublisher.Observer() {
                @Override
                public void at(
                    AdaptiveWorldBuilderPackagePublisher.Stage stage, Path packageRoot)
                    throws IOException {
                    if ("fail-written".equals(mode)
                        && stage == AdaptiveWorldBuilderPackagePublisher.Stage.PACKAGE_WRITTEN) {
                        Path path = first(packageRoot, ".raw");
                        byte[] bytes = Files.readAllBytes(path);
                        bytes[17] ^= 1;
                        Files.write(path, bytes);
                    }
                    if ("fail-terrain-rehashed".equals(mode)
                        && stage == AdaptiveWorldBuilderPackagePublisher.Stage.PACKAGE_WRITTEN) {
                        Path path = firstIn(packageRoot, "terrain", ".raw");
                        byte[] before = Files.readAllBytes(path);
                        byte[] after = before.clone();
                        after[19] ^= 1;
                        Files.write(path, after);
                        try {
                            replaceManifestHash(packageRoot, before, after);
                        } catch (Exception failure) {
                            throw new IOException(failure);
                        }
                    }
                    if ("fail-placement-rehashed".equals(mode)
                        && stage == AdaptiveWorldBuilderPackagePublisher.Stage.PACKAGE_WRITTEN) {
                        Path path = firstIn(packageRoot, "placements", ".json");
                        byte[] before = Files.readAllBytes(path);
                        String document = new String(
                            before, java.nio.charset.StandardCharsets.UTF_8);
                        byte[] after = document.replace(
                            "creator.fixture.scenery", "creator.fixture.scenerx")
                            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
                        if (java.util.Arrays.equals(before, after)) {
                            throw new IOException("fixture placement ID was not found");
                        }
                        Files.write(path, after);
                        try {
                            replaceManifestHash(packageRoot, before, after);
                        } catch (Exception failure) {
                            throw new IOException(failure);
                        }
                    }
                    if ("fail-validated".equals(mode)
                        && stage == AdaptiveWorldBuilderPackagePublisher.Stage.PACKAGE_VALIDATED) {
                        Path path = first(packageRoot, ".json");
                        byte[] bytes = Files.readAllBytes(path);
                        bytes[0] ^= 1;
                        Files.write(path, bytes);
                    }
                    if ("fail-moved".equals(mode)
                        && stage == AdaptiveWorldBuilderPackagePublisher.Stage.PREVIOUS_MOVED) {
                        throw new IOException("injected interrupted save");
                    }
                    if ("crash-moved".equals(mode)
                        && stage == AdaptiveWorldBuilderPackagePublisher.Stage.PREVIOUS_MOVED) {
                        Runtime.getRuntime().halt(73);
                    }
                }
            };
        }
        AdaptiveWorldBuilderPackagePublisher.SaveResult result =
            AdaptiveWorldBuilderPackagePublisher.publish(
                working, baseline, workingHash, baselineHash,
                draft(source, mode),
                new AdaptiveWorldBuilderPackagePublisher.PackageVerifier() {
                    @Override public void verify(NativeLayeredWorldPackage value) {}
                }, observer);
        System.out.println(result.manifestSha256 + " " + result.inventorySha256
            + " " + result.boundaryCount + " " + result.sceneryCount
            + " " + result.npcCount + " " + result.groundItemCount);
    }
}
"""


CLIENT_HARNESS = r"""
import orsc.AdaptiveWorldBuilderClientSession;
import java.nio.file.Path;
import java.nio.file.Paths;

public final class AdaptiveWorldBuilderClientBindingHarness {
    public static void main(String[] args) {
        Path binding = Paths.get(args[0]);
        AdaptiveWorldBuilderClientSession session =
            AdaptiveWorldBuilderClientSession.load(binding);
        session.requireEvidence(Paths.get(args[1]), Paths.get(args[2]));
        session.requireCredential(Paths.get(args[3]));
        session.requirePackageIdentity(args[4], args[5], args[6]);
        if (!session.allowsDefinition("boundary", 10)
                || !session.allowsDefinition("scenery", 104)
                || !session.allowsDefinition("npc", 31)
                || !session.allowsDefinition("item", 20)) {
            throw new AssertionError("authorable unused definition was hidden");
        }
        if (session.allowsDefinition("boundary", 2)
                || session.allowsDefinition("scenery", 2)
                || session.allowsDefinition("npc", 2)
                || session.allowsDefinition("item", 2)) {
            throw new AssertionError("out-of-catalog definition was exposed");
        }
        System.out.println(session.token() + " " + session.packageId());
    }
}
"""


CLIENT_STARTUP_HARNESS = r"""
import orsc.Config;
import orsc.NativeLayeredTerrainChunk;
import orsc.NativeLayeredTerrainSnapshot;
import orsc.WorldBuilderClientProfile;
import orsc.mudclient;
import orsc.graphics.three.World;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class AdaptiveWorldBuilderClientStartupHarness {
    private static final String SOURCE_REVISION =
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static String repeated(char value) {
        char[] result = new char[64];
        java.util.Arrays.fill(result, value);
        return new String(result);
    }

    private static Method worldMethod(String name, Class<?>... parameters)
            throws Exception {
        Method method = World.class.getDeclaredMethod(name, parameters);
        method.setAccessible(true);
        return method;
    }

    private static Throwable invokeFailure(
            Method method, Object receiver, Object... arguments) throws Exception {
        try {
            method.invoke(receiver, arguments);
            throw new AssertionError("strict adaptive legacy entry point was accepted");
        } catch (InvocationTargetException expected) {
            return expected.getCause();
        }
    }

    private static NativeLayeredTerrainSnapshot terrain(
            String packageId, String packageVersion, String manifest,
            String worldSpace, int level, int x, int y) {
        int centerX = Math.floorDiv(x, NativeLayeredTerrainSnapshot.SECTOR_SIZE);
        int centerY = Math.floorDiv(y, NativeLayeredTerrainSnapshot.SECTOR_SIZE);
        NativeLayeredTerrainChunk[] chunks = new NativeLayeredTerrainChunk[9];
        int index = 0;
        for (int deltaX = -1; deltaX <= 1; deltaX++) {
            for (int deltaY = -1; deltaY <= 1; deltaY++) {
                int chunkX = centerX + deltaX;
                int chunkY = centerY + deltaY;
                byte[] tiles = new byte[
                    NativeLayeredTerrainSnapshot.SECTOR_SIZE
                        * NativeLayeredTerrainSnapshot.SECTOR_SIZE
                        * NativeLayeredTerrainChunk.TILE_WIRE_BYTES];
                for (int offset = 0; offset < tiles.length;
                        offset += NativeLayeredTerrainChunk.TILE_WIRE_BYTES) {
                    tiles[offset + 2] = 1;
                    tiles[offset + 3] = 8;
                }
                chunks[index++] = NativeLayeredTerrainChunk.available(
                    NativeLayeredTerrainSnapshot.SECTOR_SIZE,
                    chunkX, chunkY, chunkX, chunkY,
                    NativeLayeredTerrainChunk.RAW_ENCODING_V2, repeated('4'), tiles);
            }
        }
        return new NativeLayeredTerrainSnapshot(
            NativeLayeredTerrainSnapshot.ATOMIC_ACTIVATION_PROTOCOL_VERSION,
            packageId, packageVersion, manifest,
            NativeLayeredTerrainSnapshot.SECTOR_SIZE,
            worldSpace, level, centerX, centerY, 1, chunks);
    }

    private static void setBaseProperties(String credential) {
        System.setProperty(WorldBuilderClientProfile.HOST_PROPERTY, "127.0.0.1");
        System.setProperty(WorldBuilderClientProfile.PORT_PROPERTY, "43615");
        System.setProperty(
            WorldBuilderClientProfile.CREDENTIAL_FILE_PROPERTY, credential);
        System.setProperty(
            WorldBuilderClientProfile.PROJECT_NAME_PROPERTY, "Adaptive Test");
        System.setProperty(
            WorldBuilderClientProfile.SOURCE_REVISION_PROPERTY, SOURCE_REVISION);
    }

    public static void main(String[] args) throws Exception {
        setBaseProperties(args[3]);
        System.setProperty(WorldBuilderClientProfile.ADAPTIVE_PROPERTY, "true");
        System.setProperty(WorldBuilderClientProfile.ENABLED_PROPERTY, "false");
        require(!WorldBuilderClientProfile.initializeFromSystemProperties()
            .isStrictAdaptiveTerrain(), "adaptive property alone activated bypass");
        require(mudclient.adaptiveRuntimeFatalExitStatus() == 0,
            "disabled adaptive profile claimed a fatal exit status");

        System.setProperty(WorldBuilderClientProfile.ADAPTIVE_PROPERTY, "false");
        System.setProperty(WorldBuilderClientProfile.ENABLED_PROPERTY, "true");
        require(!WorldBuilderClientProfile.initializeFromSystemProperties()
            .isStrictAdaptiveTerrain(), "world-builder property alone activated bypass");

        System.setProperty(WorldBuilderClientProfile.ADAPTIVE_PROPERTY, "true");
        System.setProperty(
            WorldBuilderClientProfile.RUNTIME_BINDING_FILE_PROPERTY, args[0]);
        System.setProperty(
            WorldBuilderClientProfile.DEFINITION_EVIDENCE_FILE_PROPERTY, args[1]);
        System.setProperty(
            WorldBuilderClientProfile.ASSET_EVIDENCE_FILE_PROPERTY, args[2]);
        WorldBuilderClientProfile profile =
            WorldBuilderClientProfile.initializeFromSystemProperties();
        require(profile.isStrictAdaptiveTerrain(), "strict adaptive profile missing");
        require(mudclient.adaptiveRuntimeFatalExitStatus() == 1,
            "strict adaptive profile has no fatal exit status");
        Method legacyLoginWorld = mudclient.class.getDeclaredMethod(
            "shouldRenderLegacyLoginWorld");
        legacyLoginWorld.setAccessible(true);
        require(!((Boolean) legacyLoginWorld.invoke(null)).booleanValue(),
            "strict startup enabled decorative legacy login-world rendering");
        Config.F_CACHE_DIR = args[4];

        Method reset = worldMethod("resetLegacyLandscapeReadAttemptCount");
        Method count = worldMethod("legacyLandscapeReadAttemptCount");
        reset.invoke(null);
        World world = new World(null, null);
        require(((Long) count.invoke(null)).longValue() == 0L,
            "strict startup attempted a legacy landscape read");
        require(profile.layeredManifestShort().equals(world.mapHash.substring(0, 12)),
            "strict startup map identity differs from its binding");
        require(!profile.isAdaptiveWorldStateReady(true, true),
            "world became ready before authenticated server binding");

        Method guard = worldMethod(
            "requireLegacyLandscapeArchiveReadAllowed", String.class);
        Method hash = worldMethod("generateMapHash", String.class);
        Method sector = worldMethod("readSectorTemplate", String.class, int.class);
        Throwable failure = invokeFailure(guard, null, "archive-open");
        require(failure.getMessage().contains("archive-open"),
            "archive-open tripwire was not actionable");
        failure = invokeFailure(hash, world, args[4] + "/missing.orsc");
        require(failure.getMessage().contains("archive-hash"),
            "archive-hash tripwire was not actionable");
        failure = invokeFailure(sector, world, "h0x0y0", Integer.valueOf(0));
        require(failure.getMessage().contains("sector-entry-read"),
            "sector read tripwire was not actionable");
        require(((Long) count.invoke(null)).longValue() == 3L,
            "not every strict legacy landscape entry point was instrumented");

        String packageId = profile.layeredPackageId();
        String packageVersion = profile.layeredPackageVersion();
        String manifest = args[5];
        String worldSpace = profile.layeredWorldSpace();
        int level = Integer.parseInt(args[6]);
        int x = Integer.parseInt(args[7]);
        int y = Integer.parseInt(args[8]);
        NativeLayeredTerrainSnapshot accepted = terrain(
            packageId, packageVersion, manifest, worldSpace, level, x, y);
        try {
            profile.acceptAdaptiveNativeTerrainContext(
                8, worldSpace, level, x, y, accepted);
            throw new AssertionError("terrain was accepted before server binding");
        } catch (IllegalStateException expected) {
        }
        profile.acceptAdaptiveServerBinding();
        require(!profile.isAdaptiveWorldStateReady(true, true),
            "world became ready before native terrain context");
        try {
            profile.acceptAdaptiveNativeTerrainContext(
                7, worldSpace, level, x, y, accepted);
            throw new AssertionError("unsupported adaptive protocol was accepted");
        } catch (IllegalStateException expected) {
        }
        try {
            profile.acceptAdaptiveNativeTerrainContext(
                8, worldSpace, level, x, y,
                terrain("mismatch.package", packageVersion, manifest,
                    worldSpace, level, x, y));
            throw new AssertionError("mismatched package was accepted");
        } catch (IllegalStateException expected) {
        }
        try {
            profile.acceptAdaptiveNativeTerrainContext(
                8, worldSpace, level, x, y,
                terrain(packageId, packageVersion, repeated('5'),
                    worldSpace, level, x, y));
            throw new AssertionError("mismatched manifest was accepted");
        } catch (IllegalStateException expected) {
        }
        profile.acceptAdaptiveNativeTerrainContext(
            8, worldSpace, level, x + 1, y, accepted);
        int liveLevel = 37;
        NativeLayeredTerrainSnapshot live = terrain(
            packageId, packageVersion, manifest, worldSpace, liveLevel, x, y);
        require(!profile.declaresLayer(liveLevel),
            "unpublished level was present before its terrain context");
        profile.validateAdaptiveNativeTerrainContext(
            8, worldSpace, liveLevel, x, y, live);
        require(!profile.declaresLayer(liveLevel),
            "terrain validation mutated the active level set");
        profile.acceptAdaptiveNativeTerrainContext(
            8, worldSpace, liveLevel, x, y, live);
        require(profile.declaresLayer(liveLevel),
            "authenticated live draft level was not activated");
        require(profile.layeredLevelsLabel().endsWith(",37"),
            "live draft level is absent from the active level label");
        require(!profile.isAdaptiveWorldStateReady(false, true),
            "world became ready before initial region load");
        require(!profile.isAdaptiveWorldStateReady(true, false),
            "world became ready without resident native terrain");
        require(profile.isAdaptiveWorldStateReady(true, true),
            "verified remembered-position terrain did not make adaptive world ready");
        System.out.println("strict-startup-ok");
    }
}
"""


class AdaptiveWorldBuilderRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CORE.is_file():
            raise RuntimeError("server/core.jar is required; run ./scripts/build-server.sh")
        if not CLIENT.is_file():
            raise RuntimeError(
                "Client_Base/Open_RSC_Client.jar is required; run ./scripts/build-client.sh"
            )
        cls.compiled = tempfile.TemporaryDirectory(prefix="adaptive-runtime-classes-")
        classes = Path(cls.compiled.name)
        source = classes / "AdaptiveWorldBuilderRuntimeHarness.java"
        source.write_text(textwrap.dedent(HARNESS), encoding="utf-8")
        subprocess.run(
            [
                "javac", "-source", "8", "-target", "8",
                "-cp", str(CORE), "-d", str(classes), str(source),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        client_source = classes / "AdaptiveWorldBuilderClientBindingHarness.java"
        client_source.write_text(textwrap.dedent(CLIENT_HARNESS), encoding="utf-8")
        subprocess.run(
            [
                "javac", "-source", "8", "-target", "8",
                "-cp", str(CLIENT), "-d", str(classes), str(client_source),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        startup_source = classes / "AdaptiveWorldBuilderClientStartupHarness.java"
        startup_source.write_text(
            textwrap.dedent(CLIENT_STARTUP_HARNESS), encoding="utf-8"
        )
        subprocess.run(
            [
                "javac", "-source", "8", "-target", "8",
                "-cp", str(CLIENT), "-d", str(classes), str(startup_source),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        # Exercise the same authority order installed targets use: the bounded
        # World Builder upgrade first, then the target/server fallback runtime.
        cls.classpath = os.pathsep.join(
            (str(classes), str(INSTALLED_RUNTIME), str(CORE))
        )
        cls.client_classpath = os.pathsep.join((str(classes), str(CLIENT)))

    @classmethod
    def tearDownClass(cls):
        cls.compiled.cleanup()

    def run_harness(self, mode: str, working: Path, *arguments):
        command = [
            "java", "-cp", self.classpath,
            "AdaptiveWorldBuilderRuntimeHarness", mode, str(working),
        ]
        command.extend(str(argument) for argument in arguments)
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)

    def fixture(
        self, root: Path, *, empty: bool = False,
        empty_start: tuple[int, int] = (0, 0), visible_patch: bool = False,
    ):
        working = root / "project/working/layered-world/package"
        baseline = root / "project/source/layered-baseline/package"
        target = root / "server-target"
        write_package(
            working, empty=empty, empty_start=empty_start,
            visible_patch=visible_patch,
        )
        shutil.copytree(working, baseline)
        (target / "server/maps").mkdir(parents=True)
        (target / "server/maps/live.dat").write_bytes(b"target must not change\n")
        return working, baseline, target

    def client_binding_fixture(self, root: Path, *, empty: bool = False):
        control = root / "project/run/world-builder"
        evidence = root / "project/working/runtime/client/evidence"
        control.mkdir(parents=True)
        evidence.mkdir(parents=True)
        composition = control / "effective-static-composition.json"
        composition.write_bytes(b"{}\n")
        definitions = evidence / "definitions.bin"
        assets = evidence / "assets.bin"
        definitions.write_bytes(b"content-neutral definitions\n")
        assets.write_bytes(b"content-neutral assets\n")
        credential = (
            root / "project/working/runtime/server/inc/sqlite/"
            "world-builder.credential"
        )
        credential.parent.mkdir(parents=True)
        credential.write_text("Abcdefghijk23456789Z", encoding="ascii")
        fields = {
            "assetContract": "world-builder-client-asset-binding-v1",
            "assetIdentity": "creator.assets.v1",
            "assetSha256": hashlib.sha256(assets.read_bytes()).hexdigest(),
            "authoring": "generic-signed-layered-authoring-v2-u16-elevation",
            "authorableBoundaryIds": "1,10",
            "authorableFloorIds": "0,3",
            "authorableItemIds": "10,20",
            "authorableNpcIds": "30,31",
            "authorableSceneryIds": "0,104",
            "capability": "adaptive-world-builder-runtime-capability-v5",
            "clientBuild": "rsc-world-editor-runtime-adaptive-builder-client-v5",
            "clientVersion": "10048",
            "coordinateModel": "signed-layered-v1",
            "contentAssetSha256": "",
            "contentBundleSha256": "",
            "contentCapability": "",
            "contentDefinitionSha256": "",
            "contentItemVisualSha256": "",
            "definitionContract": "world-builder-definition-catalog-binding-v1",
            "definitionIdentity": "creator.definitions.v1",
            "definitionSha256": hashlib.sha256(definitions.read_bytes()).hexdigest(),
            "effectiveComposition": "world-builder-effective-static-composition-v1",
            "effectiveCompositionSha256": hashlib.sha256(
                composition.read_bytes()
            ).hexdigest(),
            "initialLevel": "0",
            "initialWorldSpace": "global",
            "initialX": "7",
            "initialY": "9",
            "loader": "generic-signed-layered-loader-v7-blocking-base-color",
            "levels": "-3,0",
            "manifestSha256": "1" * 64,
            "packageId": "creator.arbitrary-adopted-world",
            "packageInventorySha256": "2" * 64,
            "packageSchema": "layered-world-package-v1",
            "packageVersion": "7.4.2-alpha.3",
            "placementEncoding": "layered-world-placements-v3",
            "profile": "adaptive-world-builder",
            "projectOrigin": "target-layered",
            "protocol": "world-builder-native-layered-protocol-v2-u16-elevation",
            "requiredBoundaryIds": "",
            "requiredItemIds": "",
            "requiredNpcIds": "",
            "requiredSceneryIds": "",
            "requiredTileIds": "",
            "serverBuild": "rsc-world-editor-runtime-adaptive-builder-server-v5",
            "sourceBaselineInventorySha256": "3" * 64,
        }
        if empty:
            fields.update({
                "initialLevel": "0",
                "initialX": "120",
                "initialY": "648",
                "levels": "0",
                "packageId": "creator.standalone-empty-world",
                "packageVersion": "1.0.0",
                "projectOrigin": "standalone-empty",
            })
        binding = control / "runtime-binding.properties"
        binding.write_text(
            "adaptive-world-builder-session-v1\n"
            + "".join(f"{key}={fields[key]}\n" for key in sorted(fields)),
            encoding="ascii",
        )
        return binding, definitions, assets, fields

    def run_client_binding(
        self, binding: Path, definitions: Path, assets: Path, fields: dict,
        credential: Path | None = None,
    ):
        if credential is None:
            credential = (
                binding.parents[2] / "working/runtime/server/inc/sqlite/"
                "world-builder.credential"
            )
        return subprocess.run(
            [
                "java", "-cp", self.client_classpath,
                "AdaptiveWorldBuilderClientBindingHarness",
                str(binding), str(definitions), str(assets),
                str(credential),
                fields["packageId"], fields["packageVersion"],
                fields["manifestSha256"],
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def run_client_startup(
        self, binding: Path, definitions: Path, assets: Path, fields: dict,
        cache: Path,
    ):
        credential = (
            binding.parents[2] / "working/runtime/server/inc/sqlite/"
            "world-builder.credential"
        )
        return subprocess.run(
            [
                "java", "-cp", self.client_classpath,
                "AdaptiveWorldBuilderClientStartupHarness",
                str(binding), str(definitions), str(assets), str(credential),
                str(cache), fields["manifestSha256"], fields["initialLevel"],
                fields["initialX"], fields["initialY"],
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_large_terrain_snapshot_is_complete_and_bounded(self):
        with tempfile.TemporaryDirectory(prefix="adaptive-large-snapshot-") as folder:
            working, _, _ = self.fixture(Path(folder))
            result = self.run_harness("snapshot-index", working)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("snapshot-index-ok edits=4096", result.stdout)

    def test_generic_package_publish_is_deterministic_and_preserves_all_families(self):
        outputs = []
        compositions = []
        for name in ("short", "a-very-different-absolute-root-name"):
            with tempfile.TemporaryDirectory(prefix=f"adaptive-{name}-") as temp:
                working, baseline, target = self.fixture(Path(temp))
                sibling = Path(temp) / "existing-other-project"
                sibling.mkdir()
                (sibling / "keep.txt").write_bytes(b"unrelated workspace\n")
                baseline_before = digest_tree(baseline)
                target_before = digest_tree(target)
                sibling_before = digest_tree(sibling)
                result = self.run_harness("publish", working, baseline)
                self.assertEqual(0, result.returncode, result.stderr)
                fields = result.stdout.strip().split()
                self.assertEqual(["1", "1", "1", "1"], fields[2:])
                self.assertEqual(baseline_before, digest_tree(baseline))
                self.assertEqual(target_before, digest_tree(target))
                self.assertEqual(sibling_before, digest_tree(sibling))
                self.assertEqual(
                    "creator.arbitrary-adopted-world",
                    json.loads((working / "manifest.json").read_text())["packageId"],
                )
                self.assertEqual(
                    ["creator.global.lm3", "creator.global.lp0"],
                    [
                        value["id"]
                        for value in json.loads(
                            (working / "manifest.json").read_text()
                        )["placementSets"]
                    ],
                )
                outputs.append(
                    {
                        path.relative_to(working).as_posix(): path.read_bytes()
                        for path in working.rglob("*") if path.is_file()
                    }
                )
                composition = working.parents[2] / "run/effective.json"
                composition.parent.mkdir(parents=True)
                evidence = self.run_harness(
                    "composition", working, composition
                )
                self.assertEqual(0, evidence.returncode, evidence.stderr)
                parsed = json.loads(composition.read_text())
                self.assertEqual(
                    {"boundaries": 1, "groundItems": 1, "npcs": 1, "scenery": 1},
                    parsed["counts"],
                )
                level_zero = next(
                    value for value in parsed["placementSets"]
                    if value["level"] == 0
                )
                self.assertEqual("creator.fixture.boundary", level_zero["boundaries"][0]["placementId"])
                self.assertEqual("creator.fixture.ground-item", level_zero["groundItems"][0]["placementId"])
                self.assertEqual("creator.fixture.npc", level_zero["npcs"][0]["placementId"])
                self.assertEqual("creator.fixture.scenery", level_zero["scenery"][0]["placementId"])
                self.assertRegex(level_zero["sourceSha256"], r"^[0-9a-f]{64}$")
                compositions.append(composition.read_bytes())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(compositions[0], compositions[1])

    def test_publish_canonical_sorts_lower_coordinate_additions_in_every_family(self):
        published = []
        for mode in ("canonical-forward", "canonical-reversed"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                prefix=f"adaptive-{mode}-"
            ) as temp:
                working, baseline, _ = self.fixture(Path(temp))
                result = self.run_harness(mode, working, baseline)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(
                    ["3", "2", "2", "2"],
                    result.stdout.strip().split()[2:],
                )
                placement = json.loads(
                    (working / "placements/global/lp0.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    [
                        (2, 2, 0, "zz.lower.boundary.direction-0"),
                        (2, 2, 2, "zz.lower.boundary.direction-2"),
                        (14, 14, 1, "creator.fixture.boundary"),
                    ],
                    [
                        (
                            row["position"]["x"], row["position"]["y"],
                            row["direction"], row["placementId"],
                        )
                        for row in placement["boundaries"]
                    ],
                )
                self.assertEqual(
                    [(3, 3, "zz.lower.scenery"),
                     (12, 12, "creator.fixture.scenery")],
                    [
                        (row["position"]["x"], row["position"]["y"],
                         row["placementId"])
                        for row in placement["scenery"]
                    ],
                )
                self.assertEqual(
                    [(4, 4, "zz.lower.npc"),
                     (8, 8, "creator.fixture.npc")],
                    [
                        (row["start"]["x"], row["start"]["y"],
                         row["placementId"])
                        for row in placement["npcs"]
                    ],
                )
                self.assertEqual(
                    [(5, 5, "zz.lower.ground-item"),
                     (10, 10, "creator.fixture.ground-item")],
                    [
                        (row["position"]["x"], row["position"]["y"],
                         row["placementId"])
                        for row in placement["groundItems"]
                    ],
                )
                published.append({
                    path.relative_to(working).as_posix(): path.read_bytes()
                    for path in working.rglob("*") if path.is_file()
                })
        self.assertEqual(
            published[0], published[1],
            "canonical output must not depend on input iteration order",
        )

    def test_standalone_empty_accepts_new_bound_seed_and_exact_legacy_origin(self):
        for name, start, visible in (
            ("new", (120, 648), True),
            ("legacy", (0, 0), False),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix=f"adaptive-empty-{name}-"
            ) as temp:
                working, baseline, target = self.fixture(
                    Path(temp), empty=True, empty_start=start,
                    visible_patch=visible,
                )
                result = self.run_harness("guard", working)
                self.assertEqual(0, result.returncode, result.stderr)
                result = self.run_harness(
                    "empty-origin", working, start[0], start[1]
                )
                self.assertEqual(0, result.returncode, result.stderr)
                manifest = json.loads((working / "manifest.json").read_text())
                sector = manifest["terrainSectors"][0]
                self.assertEqual([start[0] // 48, start[1] // 48], [
                    sector["sectorX"], sector["sectorY"],
                ])
                payload = (working / sector["path"]).read_bytes()
                if visible:
                    seed = 0
                    for x in range(48):
                        for y in range(48):
                            tile = payload[
                                terrain_offset(x, y):terrain_offset(x, y) + 10
                            ]
                            if 23 <= x <= 25 and 23 <= y <= 25:
                                self.assertEqual(VISIBLE_TILE, tile)
                                seed += 1
                            else:
                                self.assertEqual(VOID_TILE, tile)
                    self.assertEqual(9, seed)
                else:
                    self.assertEqual(VOID_TILE * (48 * 48), payload)
                self.assertEqual("creator.empty-world", manifest["packageId"])
                for path in working.rglob("*"):
                    if path.is_file():
                        self.assertNotIn(b"spoiled-milk", path.read_bytes().lower())

    def test_adopted_origin_retains_generic_coordinate_and_package_shape(self):
        with tempfile.TemporaryDirectory(prefix="adaptive-adopted-origin-") as temp:
            working, baseline, target = self.fixture(Path(temp))
            accepted = self.run_harness("adopted-origin", working, 7, 9)
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            self.assertIn("accepted-target-layered", accepted.stdout)
            source = json.loads((working / "manifest.json").read_text())
            self.assertEqual(2, len(source["levels"]))
            self.assertEqual(2, len(source["terrainSectors"]))
            self.assertEqual(2, len(source["placementSets"]))
            self.assertTrue(source["placementSets"][1]["path"].endswith("lp0.json"))

            uncovered = self.run_harness("adopted-origin", working, 80, 9)
            self.assertNotEqual(0, uncovered.returncode)

    def test_saved_standalone_placements_reopen_as_working_descendant(self):
        with tempfile.TemporaryDirectory(
            prefix="adaptive-empty-working-"
        ) as temp:
            working, baseline, target = self.fixture(
                Path(temp), empty=True, empty_start=(120, 648),
                visible_patch=True,
            )
            add_scenery_placement(working, 0, 119, 648)
            self.assertEqual(0, self.run_harness("guard", working).returncode)

            reopened = self.run_harness(
                "empty-working", working, baseline, 120, 648
            )
            self.assertEqual(0, reopened.returncode, reopened.stderr)
            self.assertIn("accepted-standalone-empty", reopened.stdout)

            origin_only = self.run_harness(
                "empty-origin", working, 120, 648
            )
            self.assertNotEqual(
                0, origin_only.returncode,
                "authored working content must not weaken empty-origin validation",
            )

    def test_standalone_empty_bound_seed_rejects_adversarial_shapes(self):
        start = (120, 648)

        def reset_seed(payload):
            for x in range(23, 26):
                for y in range(23, 26):
                    offset = terrain_offset(x, y)
                    payload[offset:offset + 10] = VOID_TILE

        mutations = {
            "shifted-seed": lambda payload, declaration: (
                reset_seed(payload),
                [payload.__setitem__(
                    slice(terrain_offset(x, y), terrain_offset(x, y) + 10),
                    VISIBLE_TILE,
                ) for x in range(24, 27) for y in range(23, 26)],
            ),
            "wrong-sized-seed": lambda payload, declaration: payload.__setitem__(
                slice(terrain_offset(23, 23), terrain_offset(23, 23) + 10),
                VOID_TILE,
            ),
            "wrong-color": lambda payload, declaration: payload.__setitem__(
                terrain_offset(24, 24) + 1, 1
            ),
            "wrong-overlay": lambda payload, declaration: payload.__setitem__(
                terrain_offset(24, 24) + 2, 1
            ),
            "wrong-other-field": lambda payload, declaration: payload.__setitem__(
                terrain_offset(24, 24) + 3, 1
            ),
            "extra-non-void": lambda payload, declaration: payload.__setitem__(
                slice(terrain_offset(22, 24), terrain_offset(22, 24) + 10),
                VISIBLE_TILE,
            ),
            "wrong-sector": lambda payload, declaration: declaration.__setitem__(
                "sectorX", 3
            ),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix=f"adaptive-empty-{name}-"
            ) as temp:
                working, baseline, target = self.fixture(
                    Path(temp), empty=True, empty_start=start, visible_patch=True,
                )
                mutate_first_terrain(working, mutation)
                refused = self.run_harness(
                    "empty-origin", working, start[0], start[1]
                )
                self.assertNotEqual(0, refused.returncode)

        for name, configured, package_start in (
            ("uncovered", (120, 648), (0, 0)),
            ("out-of-range-x", (32768, 648), (120, 648)),
            ("out-of-range-y", (120, 32768), (120, 648)),
            ("sector-edge", (96, 624), (96, 624)),
            ("near-sector-edge", (97, 624), (97, 624)),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix=f"adaptive-empty-{name}-"
            ) as temp:
                working, baseline, target = self.fixture(
                    Path(temp), empty=True, empty_start=package_start,
                    visible_patch=False,
                )
                refused = self.run_harness(
                    "empty-origin", working, configured[0], configured[1]
                )
                self.assertNotEqual(0, refused.returncode)

    def test_injected_failures_leave_complete_working_baseline_and_target(self):
        for mode in (
            "fail-written", "fail-terrain-rehashed", "fail-placement-rehashed",
            "fail-validated", "fail-moved",
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                prefix=f"adaptive-{mode}-"
            ) as temp:
                working, baseline, target = self.fixture(Path(temp))
                sibling = Path(temp) / "existing-other-project"
                sibling.mkdir()
                (sibling / "keep.txt").write_bytes(b"unrelated workspace\n")
                before = (
                    digest_tree(working), digest_tree(baseline),
                    digest_tree(target), digest_tree(sibling),
                )
                result = self.run_harness(mode, working, baseline)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(
                    before,
                    (
                        digest_tree(working), digest_tree(baseline),
                        digest_tree(target), digest_tree(sibling),
                    ),
                )
                parent = working.parent
                self.assertFalse((parent / "package.save-stage").exists())
                self.assertFalse((parent / "package.save-previous").exists())
                self.assertFalse((parent / "package.save-transaction").exists())
                self.assertEqual(0, self.run_harness("guard", working).returncode)

    def test_interrupted_swap_recovers_only_verified_previous_package(self):
        with tempfile.TemporaryDirectory(prefix="adaptive-recovery-") as temp:
            working, baseline, target = self.fixture(Path(temp))
            fingerprint = self.run_harness("guard", working)
            self.assertEqual(0, fingerprint.returncode, fingerprint.stderr)
            # Recovery accepts the marker hashes; use Java's guard fingerprint by
            # normalizing working first, then simulate the crash after old rename.
            normalized_working = working
            first = self.run_harness("publish", normalized_working, baseline)
            self.assertEqual(0, first.returncode, first.stderr)
            current_hash = first.stdout.split()[1]
            parent = normalized_working.parent
            previous = parent / "package.save-previous"
            stage = parent / "package.save-stage"
            transaction = parent / "package.save-transaction"
            shutil.copytree(normalized_working, stage)
            normalized_working.rename(previous)
            transaction.write_text(
                "adaptive-world-builder-save-transaction-v1\n"
                f"old={current_hash}\nnew={current_hash}\n",
                encoding="ascii",
            )
            target_before = digest_tree(target)
            baseline_before = digest_tree(baseline)
            recovered = self.run_harness("recover", normalized_working)
            self.assertEqual(0, recovered.returncode, recovered.stderr)
            self.assertTrue(normalized_working.is_dir())
            self.assertFalse(previous.exists())
            self.assertFalse(stage.exists())
            self.assertFalse(transaction.exists())
            self.assertEqual(target_before, digest_tree(target))
            self.assertEqual(baseline_before, digest_tree(baseline))

        with tempfile.TemporaryDirectory(prefix="adaptive-hard-crash-") as temp:
            working, baseline, target = self.fixture(Path(temp))
            working_before = digest_tree(working)
            baseline_before = digest_tree(baseline)
            target_before = digest_tree(target)
            interrupted = self.run_harness("crash-moved", working, baseline)
            self.assertEqual(73, interrupted.returncode)
            parent = working.parent
            self.assertFalse(working.exists())
            self.assertTrue((parent / "package.save-stage").is_dir())
            self.assertTrue((parent / "package.save-previous").is_dir())
            self.assertTrue((parent / "package.save-transaction").is_file())
            recovered = self.run_harness("recover", working)
            self.assertEqual(0, recovered.returncode, recovered.stderr)
            self.assertEqual(working_before, digest_tree(working))
            self.assertEqual(baseline_before, digest_tree(baseline))
            self.assertEqual(target_before, digest_tree(target))
            self.assertFalse((parent / "package.save-stage").exists())
            self.assertFalse((parent / "package.save-previous").exists())
            self.assertFalse((parent / "package.save-transaction").exists())

    def test_links_escapes_and_unbounded_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="adaptive-hostile-") as temp:
            root = Path(temp)
            for attack in ("symlink", "hardlink", "escape", "unbounded"):
                with self.subTest(attack=attack):
                    package = root / attack
                    write_package(package)
                    manifest = json.loads((package / "manifest.json").read_text())
                    terrain = package / manifest["terrainSectors"][0]["path"]
                    outside = root / f"{attack}-outside"
                    outside.write_bytes(terrain.read_bytes())
                    outside_before = hashlib.sha256(outside.read_bytes()).hexdigest()
                    if attack == "symlink":
                        terrain.unlink()
                        terrain.symlink_to(outside)
                    elif attack == "hardlink":
                        terrain.unlink()
                        os.link(outside, terrain)
                    elif attack == "escape":
                        manifest["terrainSectors"][0]["path"] = "../escape.raw"
                        (package / "manifest.json").write_bytes(canonical_json(manifest))
                    else:
                        (package / "too-large.bin").write_bytes(b"")
                        with (package / "too-large.bin").open("r+b") as handle:
                            handle.truncate(32 * 1024 * 1024 + 1)
                    result = self.run_harness("guard", package)
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual(
                        outside_before,
                        hashlib.sha256(outside.read_bytes()).hexdigest(),
                    )

            real_parent = root / "real-parent"
            package = real_parent / "package"
            write_package(package)
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            result = self.run_harness("guard", linked_parent / "package")
            self.assertNotEqual(0, result.returncode)

    def test_working_and_immutable_baseline_cannot_alias(self):
        with tempfile.TemporaryDirectory(prefix="adaptive-baseline-alias-") as temp:
            package = Path(temp) / "package"
            write_package(package)
            before = digest_tree(package)
            result = self.run_harness("publish", package, package)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(before, digest_tree(package))
            self.assertFalse((package.parent / "package.save-stage").exists())

    def test_client_binding_rejects_package_definition_asset_and_path_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="adaptive-client-binding-") as temp:
            root = Path(temp)
            binding, definitions, assets, fields = self.client_binding_fixture(root)
            accepted = self.run_client_binding(binding, definitions, assets, fields)
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            self.assertIn(fields["packageId"], accepted.stdout)

            for key, value in (
                ("loader", "legacy-packed-loader-v1"),
                ("authoring", "legacy-packed-authoring-v1"),
                ("protocol", "legacy-packed-protocol-v1"),
                ("coordinateModel", "legacy-packed-y-v1"),
            ):
                mismatched_fields = dict(fields)
                mismatched_fields[key] = value
                binding.write_text(
                    "adaptive-world-builder-session-v1\n"
                    + "".join(
                        f"{name}={mismatched_fields[name]}\n"
                        for name in sorted(mismatched_fields)
                    ),
                    encoding="ascii",
                )
                mismatch = self.run_client_binding(
                    binding, definitions, assets, fields
                )
                self.assertNotEqual(0, mismatch.returncode, key)
            binding.write_text(
                "adaptive-world-builder-session-v1\n"
                + "".join(f"{key}={fields[key]}\n" for key in sorted(fields)),
                encoding="ascii",
            )

            definitions.write_bytes(b"mismatched definitions\n")
            mismatch = self.run_client_binding(binding, definitions, assets, fields)
            self.assertNotEqual(0, mismatch.returncode)
            definitions.write_bytes(b"content-neutral definitions\n")

            assets.write_bytes(b"mismatched assets\n")
            mismatch = self.run_client_binding(binding, definitions, assets, fields)
            self.assertNotEqual(0, mismatch.returncode)
            assets.write_bytes(b"content-neutral assets\n")

            wrong_package = dict(fields)
            wrong_package["manifestSha256"] = "4" * 64
            mismatch = self.run_client_binding(
                binding, definitions, assets, wrong_package
            )
            self.assertNotEqual(0, mismatch.returncode)

            outside = root / "outside-assets.bin"
            outside.write_bytes(assets.read_bytes())
            mismatch = self.run_client_binding(binding, definitions, outside, fields)
            self.assertNotEqual(0, mismatch.returncode)

            credential = (
                binding.parents[2] / "working/runtime/server/inc/sqlite/"
                "world-builder.credential"
            )
            outside_credential = root / "outside-credential"
            outside_credential.write_bytes(credential.read_bytes())
            mismatch = self.run_client_binding(
                binding, definitions, assets, fields, outside_credential
            )
            self.assertNotEqual(0, mismatch.returncode)

            credential_hardlink = credential.with_name("credential-hardlink")
            os.link(credential, credential_hardlink)
            mismatch = self.run_client_binding(binding, definitions, assets, fields)
            self.assertNotEqual(0, mismatch.returncode)
            credential_hardlink.unlink()

            hardlink = assets.with_name("assets-hardlink.bin")
            os.link(assets, hardlink)
            mismatch = self.run_client_binding(binding, definitions, assets, fields)
            self.assertNotEqual(0, mismatch.returncode)
            hardlink.unlink()

            real_binding = binding.with_name("binding-real.properties")
            binding.rename(real_binding)
            binding.symlink_to(real_binding)
            mismatch = self.run_client_binding(binding, definitions, assets, fields)
            self.assertNotEqual(0, mismatch.returncode)

    def test_client_accepts_bound_standalone_start_and_rejects_invalid_carrier(self):
        with tempfile.TemporaryDirectory(prefix="adaptive-client-empty-start-") as temp:
            root = Path(temp)
            binding, definitions, assets, fields = self.client_binding_fixture(
                root, empty=True
            )
            accepted = self.run_client_binding(binding, definitions, assets, fields)
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            self.assertEqual("120", fields["initialX"])
            self.assertEqual("648", fields["initialY"])

            for key, value in (
                ("initialX", "-1"),
                ("initialX", "32768"),
                ("initialY", "-1"),
                ("initialY", "32768"),
                ("initialLevel", "1"),
            ):
                invalid = dict(fields)
                invalid[key] = value
                binding.write_text(
                    "adaptive-world-builder-session-v1\n"
                    + "".join(
                        f"{name}={invalid[name]}\n" for name in sorted(invalid)
                    ),
                    encoding="ascii",
                )
                refused = self.run_client_binding(
                    binding, definitions, assets, invalid
                )
                self.assertNotEqual(0, refused.returncode, (key, value))

    def test_strict_startup_skips_legacy_archives_login_world_and_gates_native_readiness(self):
        for empty in (False, True):
            with self.subTest(empty=empty), tempfile.TemporaryDirectory(
                prefix="adaptive-client-startup-"
            ) as temp:
                root = Path(temp)
                binding, definitions, assets, fields = self.client_binding_fixture(
                    root, empty=empty
                )
                cache = root / "absent-legacy-cache"
                cache.mkdir()
                self.assertFalse(
                    (cache / "video/Authentic_Landscape.orsc").exists()
                )
                self.assertFalse(
                    (cache / "video/Custom_Landscape.orsc").exists()
                )
                result = self.run_client_startup(
                    binding, definitions, assets, fields, cache
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("strict-startup-ok\n", result.stdout)

    def test_strict_startup_guards_first_render_editor_and_server_scene_state(self):
        world = (ROOT / "Client_Base/src/orsc/graphics/three/World.java").read_text()
        profile = (
            ROOT / "Client_Base/src/orsc/WorldBuilderClientProfile.java"
        ).read_text()
        packets = (ROOT / "Client_Base/src/orsc/PacketHandler.java").read_text()
        client = (ROOT / "Client_Base/src/orsc/mudclient.java").read_text()
        editor = (
            ROOT / "Client_Base/src/com/openrsc/interfaces/misc/"
            "WorldEditorInterface.java"
        ).read_text()
        updater = (ROOT / "server/src/com/openrsc/server/GameStateUpdater.java").read_text()
        session = (
            ROOT / "server/src/com/openrsc/server/content/worldedit/"
            "WorldBuilderPlayerSession.java"
        ).read_text()

        strict_branch = world.index("WorldBuilderTerrainBootstrap.isNativeOnly()")
        archive_choice = world.index("Authentic_Landscape.orsc")
        self.assertLess(strict_branch, archive_choice)
        for entry in ("archive-open", "archive-hash", "sector-entry-read"):
            self.assertIn(
                f'requireLegacyLandscapeArchiveReadAllowed("{entry}")', world
            )
        self.assertIn("LEGACY_LANDSCAPE_READ_ATTEMPTS.incrementAndGet()", world)
        self.assertIn(
            "!WorldBuilderTerrainBootstrap.isNativeOnly()", world
        )
        self.assertIn("adaptiveServerBindingAccepted", profile)
        self.assertIn("adaptiveNativeContextAccepted", profile)
        context_validate = packets.index("validateAdaptiveNativeTerrainContext(")
        context_accept = packets.index("acceptAdaptiveNativeTerrainContext(")
        scene_accept = packets.index("layeredSceneContextState.accept(")
        self.assertLess(context_validate, scene_accept)
        self.assertLess(scene_accept, context_accept)
        self.assertIn("acceptAdaptiveServerBinding()", packets)
        login_render = client.split(
            "private void renderLoginScreenViewports", 1
        )[1].split("private void resetGame", 1)[0]
        self.assertLess(
            login_render.index("if (!shouldRenderLegacyLoginWorld())"),
            login_render.index("this.loadWorldComponents();"),
            "strict startup must bypass the legacy login-world before it loads",
        )
        adaptive_login = client.split(
            "private void renderAdaptiveLoginScreenViewports", 1
        )[1].split("private static boolean shouldRenderLegacyLoginWorld", 1)[0]
        self.assertIn("storeSpriteVert(", adaptive_login)
        self.assertNotIn("this.world", adaptive_login)
        self.assertIn(
            "requireLegacyLoginWorldRenderingAllowed();", client
        )
        self.assertIn(
            "Strict adaptive World Builder forbids legacy login-world rendering",
            client,
        )
        self.assertIn(
            "static int adaptiveRuntimeFatalExitStatus()", client
        )
        self.assertIn(
            "System.exit(ADAPTIVE_RUNTIME_FATAL_EXIT_STATUS);", client
        )
        self.assertIn("if (!isAdaptiveWorldStateReadyForEditor()) {", client)
        self.assertIn("drawLoadingPleaseWaitFrame();", client)
        self.assertIn("!isAdaptiveWorldStateReadyForEditor())return", client)
        self.assertGreaterEqual(editor.count("isAdaptiveWorldStateReadyForEditor()"), 2)
        self.assertIn("WorldBuilderPlayerSession.mayReceiveWorldState(player)", updater)
        self.assertIn("public static boolean mayReceiveWorldState", session)

    def test_discovery_evidence_is_strict_path_independent_and_version_bound(self):
        outputs = []
        for prefix in ("brief", "different-absolute-root"):
            with tempfile.TemporaryDirectory(prefix=f"adaptive-evidence-{prefix}-") as temp:
                catalog = Path(temp) / "working/evidence/catalog.bin"
                catalog.parent.mkdir(parents=True)
                catalog.write_bytes(b"content-neutral catalog\n")
                result = subprocess.run(
                    [
                        str(EVIDENCE_WRITER), "--side", "server",
                        "--definition-catalog", str(catalog),
                        "--definition-catalog-id", "creator.catalog.v1",
                    ],
                    cwd=ROOT, capture_output=True, check=True,
                )
                outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        evidence = json.loads(outputs[0])
        self.assertEqual("world-builder-runtime-evidence", evidence["manifestType"])
        self.assertEqual("rsc-world-editor-runtime-adaptive-builder-server-v5", evidence["buildId"])
        self.assertEqual("generic-signed-layered-loader-v7-blocking-base-color", evidence["loaderId"])
        self.assertEqual("world-builder-native-layered-protocol-v2-u16-elevation", evidence["protocolId"])
        self.assertEqual([1, 2, 3, 4], evidence["encodingVersions"])
        self.assertEqual(
            ["boundary", "ground-item", "npc", "scenery"],
            evidence["authoring"]["placementFamilies"],
        )

        capability = json.loads((
            ROOT / "server/conf/world-builder/adaptive-runtime-capability-v5.json"
        ).read_text())
        server_identity = (
            ROOT / "server/src/com/openrsc/server/content/worldedit/"
            "AdaptiveWorldBuilderRuntimeIdentity.java"
        ).read_text()
        client_identity = (
            ROOT / "Client_Base/src/orsc/AdaptiveWorldBuilderClientSession.java"
        ).read_text()
        for key in (
            "capabilityId", "serverBuildId", "clientBuildId", "loaderId",
            "authoringId", "definitionContractId", "assetContractId",
            "protocolId", "effectiveCompositionId", "packageSchemaId",
        ):
            self.assertIn(f'"{capability[key]}"', server_identity)
            self.assertIn(f'"{capability[key]}"', client_identity)
        self.assertEqual(
            [0, 1, 8, 0, 0, 0, 0, 0, 0, 0],
            capability["canonicalVoidTile"],
        )
        with tempfile.TemporaryDirectory(prefix="adaptive-evidence-link-") as temp:
            root = Path(temp)
            catalog = root / "catalog.bin"
            catalog.write_bytes(b"catalog\n")
            hardlink = root / "catalog-hardlink.bin"
            os.link(catalog, hardlink)
            refused = subprocess.run(
                [
                    str(EVIDENCE_WRITER), "--side", "client",
                    "--definition-catalog", str(catalog),
                    "--definition-catalog-id", "creator.catalog.v1",
                ],
                cwd=ROOT, capture_output=True,
            )
            self.assertNotEqual(0, refused.returncode)
            hardlink.unlink()
            linked = root / "catalog-linked.bin"
            linked.symlink_to(catalog)
            refused = subprocess.run(
                [
                    str(EVIDENCE_WRITER), "--side", "client",
                    "--definition-catalog", str(linked),
                    "--definition-catalog-id", "creator.catalog.v1",
                ],
                cwd=ROOT, capture_output=True,
            )
            self.assertNotEqual(0, refused.returncode)

    def test_fixed_profiles_and_content_neutral_policy_remain_explicit(self):
        profile = (ROOT / "server/src/com/openrsc/server/io/NativeLayeredWorldRuntimeProfile.java").read_text()
        self.assertIn('PRESERVATION_R64_REPLACEMENT("preservation-r64-replacement", true)', profile)
        self.assertIn('SPOILED_MILK_REPLACEMENT("spoiled-milk-replacement", true)', profile)
        self.assertIn('WORLD_BUILDER_INSTALLED("world-builder-installed", true)', profile)
        self.assertIn('ADAPTIVE_WORLD_BUILDER("adaptive-world-builder", true)', profile)
        self.assertNotIn("ADAPTIVE_WORLD_BUILDER = SPOILED", profile)
        installed = json.loads((
            ROOT / "server/conf/world-builder/installed-runtime-capability-v2.json"
        ).read_text())
        self.assertEqual(
            "world-builder-installed-runtime-capability",
            installed["manifestType"],
        )
        self.assertEqual("world-builder-installed", installed["profileId"])
        self.assertEqual(
            "world-builder-managed-runtime-current",
            installed["managedRuntimeBundleId"],
        )
        self.assertEqual(
            "world-builder-installed-client-profile-v1",
            installed["clientBootstrapId"],
        )
        self.assertEqual([1, 2, 3, 4], installed["encodingVersions"])
        self.assertEqual(
            "server/world-builder-runtime/world-builder-managed-runtime.jar",
            installed["runtimeArchives"]["serverRelativePath"],
        )
        self.assertEqual(
            "server/core.jar",
            installed["runtimeArchives"]["targetFallbackRelativePath"],
        )
        self.assertFalse(installed["activation"]["builderOnly"])
        self.assertTrue(installed["activation"]["replacesLegacyTerrain"])
        self.assertTrue(installed["activation"]["replacesLegacyPlacements"])
        self.assertTrue(
            installed["activation"]["replacesLegacyClientBootstrap"]
        )
        self.assertIn(
            "layered_native_terrain_package_path",
            installed["activation"]["requiredStringKeys"],
        )
        bundle = json.loads((
            ROOT / "server/conf/world-builder/managed-runtime-bundle.json"
        ).read_text())
        self.assertEqual(
            "world-builder-managed-runtime-bundle", bundle["manifestType"]
        )
        self.assertEqual(
            installed["managedRuntimeBundleId"], bundle["bundleId"]
        )
        self.assertEqual(installed["profileId"], bundle["profileId"])
        self.assertEqual(installed["loaderId"], bundle["loaderId"])
        self.assertEqual(installed["protocolId"], bundle["protocolId"])
        self.assertEqual(
            installed["clientBootstrapId"], bundle["clientBootstrapId"]
        )
        self.assertEqual(
            [
                "server-runtime-upgrade",
                "client-source-upgrade",
                "runtime-capability",
            ],
            [component["role"] for component in bundle["components"]],
        )
        self.assertEqual(
            "server/world-builder-runtime/world-builder-managed-runtime.jar",
            bundle["components"][0]["sourceRelativePath"],
        )
        self.assertEqual(
            "server/world-builder-runtime/world-builder-managed-runtime.jar",
            bundle["components"][0]["destinationRelativePath"],
        )
        self.assertEqual(
            ["server/conf/world-builder/installed-runtime-capability-v1.json"],
            bundle["legacyCapabilityPaths"],
        )
        self.assertIn("target-owned gameplay", " ".join(bundle["serverUpgradeBoundary"]))
        self.assertIn(
            "target client protocol version",
            " ".join(bundle["clientUpgradeBoundary"]),
        )
        source_upgrade = json.loads((
            ROOT / "server/conf/world-builder/installed-client-source-upgrade-v5.json"
        ).read_text())
        self.assertEqual(
            "world-builder-installed-client-source-upgrade",
            source_upgrade["manifestType"],
        )
        self.assertEqual(
            installed["clientSourceUpgrade"]["upgradeId"],
            source_upgrade["upgradeId"],
        )
        self.assertEqual(
            "atomic-compile-target-client-before-run",
            source_upgrade["buildPolicy"],
        )
        self.assertEqual(
            [
                "src/orsc/AdaptiveWorldBuilderClientSession.java",
                "src/orsc/ProjectContentBundle.java",
                "src/orsc/ProjectNpcAnimationRegistry.java",
                "src/orsc/NativeLayeredTerrainChunk.java",
                "src/orsc/NativeLayeredTerrainPacketDecoder.java",
                "src/com/openrsc/client/model/Tile.java",
                "src/orsc/WorldBuilderClientProfile.java",
                "src/orsc/WorldBuilderInstalledClientProfile.java",
                "src/orsc/WorldBuilderTerrainBootstrap.java",
                "src/orsc/WorldBuilderTerrainOverlay.java",
                "src/orsc/graphics/three/World.java",
            ],
            [entry["destinationRelativePath"] for entry in source_upgrade["sourceFiles"]],
        )
        for entry in source_upgrade["sourceFiles"]:
            source = ROOT / "Client_Base" / entry["destinationRelativePath"]
            self.assertEqual(
                entry["sha256"], hashlib.sha256(source.read_bytes()).hexdigest()
            )
        self.assertEqual(
            [
                {
                    "transformId": "world-builder-installed-login-world-bootstrap-v2",
                    "destinationRelativePath": "src/orsc/mudclient.java",
                },
                {
                    "transformId": "world-builder-unsigned-uniform-elevation-v1",
                    "destinationRelativePath": "src/orsc/NativeLayeredTerrainSnapshot.java",
                },
            ],
            source_upgrade["semanticTransforms"],
        )
        self.assertEqual(
            5,
            sum(
                entry["replacementPolicy"] == "replace-supported-historical"
                for entry in source_upgrade["sourceFiles"]
            ),
        )
        self.assertEqual(
            [
                {
                    "sourceRelativePath": "server/lib/json-20190722.jar",
                    "destinationRelativePath": "PC_Client/lib/json-20190722.jar",
                    "sha256": hashlib.sha256(
                        (ROOT / "server/lib/json-20190722.jar").read_bytes()
                    ).hexdigest(),
                    "replacementPolicy": "add-or-exact",
                }
            ],
            source_upgrade["dependencies"],
        )

        self.assertTrue(
            INSTALLED_RUNTIME.is_file(),
            "installed server upgrade is required; run ./scripts/build-server.sh",
        )
        with zipfile.ZipFile(INSTALLED_RUNTIME) as archive:
            installed_entries = set(archive.namelist())
        for required in (
            "com/openrsc/server/io/NativeLayeredWorldPackage.class",
            "com/openrsc/server/model/world/World.class",
            "com/openrsc/server/model/world/coordinate/WorldCoordinate.class",
            "com/openrsc/server/net/rsc/NativeLayeredTerrainClientResidency.class",
        ):
            self.assertIn(required, installed_entries)
        for forbidden_prefix in (
            "com/openrsc/server/content/minigame/",
            "com/openrsc/server/plugins/",
            "org/apache/",
            "org/slf4j/",
            "com/google/",
        ):
            self.assertFalse(
                any(name.startswith(forbidden_prefix) for name in installed_entries),
                f"installed server upgrade leaked target-owned {forbidden_prefix}",
            )
        publisher = (ROOT / "server/src/com/openrsc/server/content/worldedit/AdaptiveWorldBuilderPackagePublisher.java").read_text()
        self.assertNotIn("rsc-remastered.spoiled-milk-layered-world", publisher)
        self.assertNotIn("SPOILED_MILK_PACKAGE", publisher)
        sessions = (ROOT / (
            "server/src/com/openrsc/server/content/worldedit/"
            "WorldEditorSessionManager.java"
        )).read_text()
        self.assertIn('"world-builder.authored."+family', sessions)
        self.assertIn("legacyNativeSceneryPlacementId", sessions)
        async_save = sessions[
            sessions.index("public void saveAdaptivePackageAsync("):
            sessions.index("private PreparedAdaptiveSave prepareAdaptiveSave(")
        ]
        self.assertIn("prepareAdaptiveSaveInputs(player)", async_save)
        self.assertIn('"World Builder Package Save"', async_save)
        self.assertNotIn("adaptiveDraft(owner)", async_save)
        self.assertIn("indexNativeTerrainEditsBySector()", sessions)
        self.assertIn(
            "terrainEditsBySector.get(sector.getIdentity())", sessions
        )
        player_service = (
            ROOT / "server/src/com/openrsc/server/service/PlayerService.java"
        ).read_text()
        adaptive = player_service.index(
            "AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(configuration)"
        )
        production_recovery = player_service.index(
            "LayeredPlayerLoginRecovery.resolve("
        )
        self.assertLess(adaptive, production_recovery)
        self.assertIn(
            "AdaptiveWorldBuilderRuntimeIdentity.PLAYER_LOCATION_ORIGIN",
            player_service,
        )
        self.assertIn(
            "LayeredPlayerLocationPersistence.restore(", player_service
        )
        self.assertIn('remember ? "remembered" : "initialized"', player_service)
        login_handler = (
            ROOT / "server/src/com/openrsc/server/net/rsc/LoginPacketHandler.java"
        ).read_text()
        self.assertIn(
            "!AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(\n"
            "\t\t\t\tloadedPlayer.getConfig())",
            login_handler,
        )
        self.assertEqual(
            5,
            login_handler.count(
                "applyFirstTimeLocation(loadedPlayer, firstTimeLocation);"
            ),
        )
        self.assertNotIn(
            "if (loadedPlayer.getLastLogin() == 0L)", login_handler
        )
        player_session = (
            ROOT / "server/src/com/openrsc/server/content/worldedit/"
            "WorldBuilderPlayerSession.java"
        ).read_text()
        self.assertNotIn("player.teleportLayered(initial", player_session)
        self.assertIn("if(destinationMissing){", sessions)
        self.assertIn("if(destinationMissing&&!isAdaptive(player)){", sessions)
        commands = (
            ROOT / "server/src/com/openrsc/server/net/rsc/handlers/CommandHandler.java"
        ).read_text()
        self.assertIn(
            '"builderbind".equalsIgnoreCase(cmd)\n'
            "\t\t\t&& AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(",
            commands,
        )
        editor_access = (
            ROOT / "server/src/com/openrsc/server/content/worldedit/"
            "WorldEditorAccessService.java"
        ).read_text()
        self.assertIn(
            "WorldBuilderPlayerSession.mayOpenEditor(player)", editor_access
        )
        provisioner = (
            ROOT / "server/src/com/openrsc/server/content/worldedit/"
            "WorldBuilderAccountProvisioner.java"
        ).read_text()
        self.assertIn(
            'validateGeneratedPath(\n\t\t\t\tcredentialPath, '
            '"adaptive World Builder credential file")',
            provisioner,
        )
        control = (
            ROOT / "server/src/com/openrsc/server/content/worldedit/"
            "WorldBuilderRuntimeControl.java"
        ).read_text()
        self.assertIn(
            "allowedRoot.resolve(DEFAULT_CONTROL_DIRECTORY).normalize()",
            control,
        )


if __name__ == "__main__":
    unittest.main()

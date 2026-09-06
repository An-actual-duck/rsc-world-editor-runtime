"""Closed, read-only public map fixture and independent c0102 collision oracle.

This is test evidence only, never a runtime profile or promotion authority.
The input is an explicitly supplied Editor derivation, not a caller's target.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import xml.etree.ElementTree as ET
from collections import Counter

HISTORICAL_COMMIT = "c0102e60774ab9c9076aabae49f6f97fb6fc4b00"
HISTORICAL_TREE = "6db5536d795abf34f303bb03b20c43b8cfb9e3fe"
HISTORICAL_LOADER_SHA256 = "24eda72c42d5e7befb69b8e0f493cfa90f64b39f15edbf44ac5a4b824ae3db79"
SEALED = {
    "conversion/package/manifest.json": "b580ff70b2a409ef0ee0fe1f7c5ad57d7b9613af62e8cbcdf3e275877b714506",
    "conversion/discovery-reconciliation.json": "de2db1d3f32d09a906638f2c24af9a42cacbf4309c688912b3be734030a7ef3b",
    "source/migration/input/derivation.json": "2935ce8dece731b0c77c7738f03cfa6978e30c5be13b3059cf7b20829bb55000",
    "source/migration/decoder/evidence.json": "e9fb4383d7b14efe5a4919abc9b54740625393a3f23d68cfa4cc5cbf5e5a3845",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(root, relative, expected=None, size=None):
    relative = str(relative)
    parts = PurePosixPath(relative)
    if parts.is_absolute() or str(parts) != relative or ".." in parts.parts or "\\" in relative:
        raise ValueError("nonliteral fixture path: " + relative)
    path = root / relative
    if path.resolve() != path:
        raise ValueError("aliased fixture path: " + relative)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 64 * 1024 * 1024:
        raise ValueError("unsafe fixture file: " + relative)
    data = path.read_bytes()
    if size is not None and len(data) != size or expected is not None and digest(data) != expected:
        raise ValueError("fixture identity drift: " + relative)
    return data


def exact_tree(root, allowed):
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("fixture symlink")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(allowed):
        raise ValueError("fixture file inventory mismatch")


def inspect(requested):
    root = Path(requested)
    if not root.is_absolute() or root.resolve() != root or not root.is_dir():
        raise ValueError("fixture requires literal canonical existing project-stage")
    documents = {name: json.loads(checked_file(root, name, sha)) for name, sha in SEALED.items()}
    manifest = documents["conversion/package/manifest.json"]
    derivation = documents["source/migration/input/derivation.json"]
    decoded = documents["source/migration/decoder/evidence.json"]
    derived_root = root / "source/migration/input"
    for row in derivation["inputInventory"]:
        checked_file(derived_root, row["relativePath"], row["sha256"], row["size"])
    exact_tree(derived_root, [row["relativePath"] for row in derivation["inputInventory"]] + ["derivation.json"])
    reconciliation = json.loads(checked_file(derived_root, "reconciliation.json"))
    if (reconciliation["historicalSourceCommit"] != HISTORICAL_COMMIT
            or reconciliation["historicalSourceTree"] != HISTORICAL_TREE
            or reconciliation["runtimePromotionApproved"] is not False
            or derivation["runtimePromotionApproved"] is not False):
        raise ValueError("historical source/promotion identity")
    for row in reconciliation["sourceInventory"]:
        checked_file(root / "source/original", row["relativePath"], row["sha256"], row["size"])
    sectors = root / "source/migration/decoder/sectors"
    present = [row for row in decoded["inventory"] if row["present"]]
    if len(decoded["inventory"]) != 1680 or len(present) != 352:
        raise ValueError("incomplete decoder inventory")
    for row in present:
        checked_file(sectors, row["relativePath"], row["sha256"], row["size"])
    exact_tree(sectors, [row["relativePath"] for row in present])
    package = root / "conversion/package"
    records = manifest["terrainSectors"] + manifest["placementSets"]
    for row in records:
        checked_file(package, row["path"], row["sha256"])
    exact_tree(package, [row["path"] for row in records] + ["manifest.json"])
    if len(manifest["terrainSectors"]) != 352 or len(reconciliation["excludedClientSectors"]) != 1412:
        raise ValueError("canonical coverage changed")
    return root, manifest, decoded, reconciliation


def terrain_oracle(root, decoded, destination):
    """Forward-scatter the original loader's writes, not native neighbor derivation.

    c0102 WorldLoader.loadSection: x-major sectors, y-major tile visitation;
    Tile.pack itself is x-major. Overlay is a signed byte after the250→2 alias.
    Wall writes reach negative-axis neighbors. Missing sectors stay outside the
    comparison domain; current explicit blocked void is tested independently.
    """
    definitions = root / "source/original/server/conf/server/defs"
    tiles = list(ET.fromstring((definitions / "TileDef.xml").read_bytes()))
    doors = list(ET.fromstring((definitions / "DoorDef.xml").read_bytes()))
    blocking = lambda wall: wall > 0 and int(doors[wall - 1].findtext("unknown")) == 0 and int(doors[wall - 1].findtext("doorType")) != 0
    projectile_ids = {5, 6, 14, 42, 63, 128, 229, 230}
    raw, masks, projectiles, counts = {}, {}, {}, {}
    for row in decoded["inventory"]:
        if not row["present"]:
            continue
        key = (row["plane"], row["archiveX"] - 48, row["archiveY"] - 37)
        raw[key] = (root / "source/migration/decoder/sectors" / row["relativePath"]).read_bytes()
        masks[key], projectiles[key], counts[key] = bytearray(2304), bytearray(2304), bytearray(2304)

    def write(plane, x, y, mask, projectile):
        key, index = (plane, x // 48, y // 48), (x % 48) * 48 + y % 48
        if key in raw:
            masks[key][index] |= mask
            if projectile:
                projectiles[key][index] = 1
                counts[key][index] += 1

    for key in sorted(raw):
        plane, sx, sy = key
        for y in range(48):
            for x in range(48):
                index = x * 48 + y
                elevation, texture, overlay, roof, horizontal, vertical, diagonal = struct.unpack_from(
                    ">6Bi", raw[key], index * 10)
                # Preserve c0102 short diagonal and signed-byte overlay semantics.
                diagonal = (diagonal + 32768) % 65536 - 32768
                masks[key][index] = 0
                collision_overlay = 2 if overlay == 250 else overlay if overlay < 128 else overlay - 256
                if collision_overlay > 0 and int(tiles[collision_overlay - 1].findtext("objectType")) != 0:
                    masks[key][index] |= 64
                bx, by = sx * 48 + x, sy * 48 + y
                for wall, own, reciprocal, dx, dy in ((vertical, 1, 4, 0, -1), (horizontal, 2, 8, -1, 0)):
                    if blocking(wall):
                        shot = wall in projectile_ids
                        write(plane, bx, by, own, shot)
                        write(plane, bx + dx, by + dy, reciprocal, shot)
                if 0 < diagonal < 12000 and blocking(diagonal):
                    write(plane, bx, by, 32, diagonal & 255 in projectile_ids)
                if 12000 < diagonal < 24000 and blocking(diagonal - 12000):
                    write(plane, bx, by, 16, diagonal & 255 in projectile_ids)
                if overlay in (2, 11):
                    projectiles[key][index] = 1
    with destination.open("wb") as output:
        output.write(struct.pack(">i", 352 * 2304))
        for key in sorted(raw):
            plane, sx, sy = key
            for index in range(2304):
                tile = struct.unpack_from(">6Bi", raw[key], index * 10)
                output.write(struct.pack(">11i", sx * 48 + index // 48, sy * 48 + index % 48,
                    (0, 1, 2, -1)[plane], tile[2], tile[4], tile[5], (tile[6] + 32768) % 65536 - 32768,
                    masks[key][index], projectiles[key][index], counts[key][index], int(tile[2] in (2, 11))))
    return masks, projectiles


def placement_oracle(root, terrain, destination, diagnostic_tree_branch=False):
    """c0102 World.registerGameObject geometry and projectile booleans, independently.

    Original World.java SHA540bf30ae801822c93fd54a936f3e34633494473e99e3dd5e0977167a960539c.
    Original Constants.java SHAf3b04a325a9b518ca7827c27976cf29094c1ba2dbd60af88e376f820132befe5.
    Effective source composition is last scenery at position / boundary at direction.
    """
    masks, projectiles = ({key: bytearray(value) for key,value in part.items()} for part in terrain)
    definitions = root / "source/original/server/conf/server/defs"
    scenery = list(ET.fromstring((definitions / "GameObjectDef.xml").read_bytes()))
    boundaries = list(ET.fromstring((definitions / "DoorDef.xml").read_bytes()))
    names = {"gravestone", "sign", "broken pillar", "bone", "animalskull", "skull", "egg", "eggs",
             "ladder", "torch", "rock", "treestump", "railing", "railings", "gate", "fence", "table",
             "smashed chair", "smashed table", "longtable", "wooden gate", "metal gate", "chair"}

    def write(plane,x,y,mask=0,shot=False):
        key,index=(plane,x//48,y//48),(x%48)*48+y%48
        if key in masks:
            masks[key][index] |= mask
            if shot: projectiles[key][index]=1

    for kind, files, container in ((0,("SceneryLocs.json","SceneryLocsDiscontinued.json"),"sceneries"),
                                   (1,("BoundaryLocs.json",),"boundaries")):
        effective = {}
        for name in files:
            for row in json.loads((root / "source/migration/input/placements" / name).read_text())[container]:
                key=(row["pos"]["X"],row["pos"]["Y"],row["direction"] if kind else 0)
                effective[key]=row
        if len(effective) != (26815 if kind == 0 else 967):
            raise ValueError("historical effective object composition differs")
        for row in effective.values():
            object_id,direction=row["id"],row["direction"]
            if object_id == 1147: continue
            definition=(scenery if kind == 0 else boundaries)[object_id]
            object_type=int(definition.findtext("type" if kind == 0 else "doorType"))
            if kind == 0 and object_type not in (1,2) or kind == 1 and object_type != 1: continue
            name=definition.findtext("name").lower()
            width=int(definition.findtext("width")) if kind == 0 else 1
            height=int(definition.findtext("height")) if kind == 0 else 1
            shot=name in names or kind == 0 and name not in ("tree","chest") and width == height == 1
            # Diagnostic counterfactual only: never substitutes for the historical oracle.
            if diagnostic_tree_branch and kind == 0 and "tree" in name:
                shot=True
            if kind == 0 and direction not in (0,4): width,height=height,width
            plane=row["pos"]["Y"]//944
            for x in range(row["pos"]["X"],row["pos"]["X"]+width):
                for y in range(row["pos"]["Y"]%944,row["pos"]["Y"]%944+height):
                    if shot:
                        write(plane,x,y,shot=True)
                        if not (kind == 0 and object_type == 1):
                            dx,dy={0:(-1,0),2:(0,1),4:(1,0),6:(0,-1)}.get(direction,(0,0))
                            write(plane,x+dx,y+dy,shot=True)
                    if kind == 0 and object_type == 1:
                        write(plane,x,y,64)
                    else:
                        shape=({0:(2,8,-1,0),2:(4,1,0,1),4:(8,2,1,0),6:(1,4,0,-1)} if kind == 0
                               else {0:(1,4,0,-1),1:(2,8,-1,0),2:(16,0,0,0),3:(32,0,0,0)}).get(direction)
                        if shape:
                            own,neighbor,dx,dy=shape
                            write(plane,x,y,own)
                            write(plane,x+dx,y+dy,neighbor)
    with destination.open("wb") as output:
        output.write(struct.pack(">i",811008))
        for key in sorted(masks):
            plane,sx,sy=key
            for index in range(2304):
                output.write(struct.pack(">5i",sx*48+index//48,sy*48+index%48,(0,1,2,-1)[plane],
                                         masks[key][index],projectiles[key][index]))


def npc_expectations(root, manifest, destination):
    original = Counter()
    for name in ("NpcLocs.json", "NpcLocsDiscontinued.json"):
        source = json.loads((root / "source/migration/input/placements" / name).read_text())
        for row in source["npclocs"]:
            start, low, high = row["start"], row["min"], row["max"]
            original[(row["id"], (0,1,2,-1)[start["Y"] // 944], start["X"], start["Y"] % 944,
                      low["X"], low["Y"] % 944, high["X"], high["Y"] % 944, -1)] += 1
    canonical, lines = Counter(), []
    for declaration in manifest["placementSets"]:
        body = json.loads((root / "conversion/package" / declaration["path"]).read_text())
        for row in body["npcs"]:
            start, low, high = row["start"], row["roamBounds"]["minimum"], row["roamBounds"]["maximum"]
            key = (row["npcId"], body["level"], start["x"], start["y"],
                   low["x"], low["y"], high["x"], high["y"], row["respawnSeconds"])
            canonical[key] += 1
            lines.append(row["placementId"] + "\t" + "\t".join(map(str,key)))
    if original != canonical or sum(original.values()) != 3609:
        raise ValueError("canonical NPC multiset differs from sealed historical derivation")
    destination.write_text("\n".join(sorted(lines)) + "\n")

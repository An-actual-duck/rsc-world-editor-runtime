#!/usr/bin/env python3

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
DEFS = ROOT / "server" / "conf" / "server" / "defs"
ENTITY_HANDLER = ROOT / "server" / "src" / "com" / "openrsc" / "server" / "external" / "EntityHandler.java"
FIXTURES = ROOT / "tests" / "myworld" / "fixtures"
SERVER_CORE = ROOT / "server" / "core.jar"
SERVER_PLUGINS = ROOT / "server" / "plugins.jar"

NPC_FIELDS = {
    "id", "name", "description", "command", "attack", "strength", "hits", "defense", "ranged",
    "projectileRange",
    "meleeOffense", "rangedOffense", "magicOffense",
    "meleeDefense", "rangedDefense", "magicDefense", "meleeDefenseMultiplier",
    "rangedDefenseMultiplier", "magicDefenseMultiplier", "meleeDefenseDivisor",
    "rangedDefenseDivisor", "magicDefenseDivisor", "combatlvl", "hairColour",
    "topColour", "bottomColour", "skinColour",
}
ITEM_FIELDS = {
    "id", "name", "description", "meleeOffense", "rangedOffense", "magicOffense",
    "weaponSpeed", "meleeDefense", "rangedDefense", "magicDefense", "requiredLevel",
    "requiredSkillID", "isWearable", "appearanceID", "wearableID", "wearSlot",
    "weaponAimBonus", "weaponPowerBonus", "armourBonus", "magicBonus", "prayerBonus",
    "basePrice",
}


def load_entries(filename: str) -> list[dict]:
    data = json.loads((DEFS / filename).read_text(encoding="utf-8"))
    return data[next(iter(data))]


def definition_ids(*filenames: str) -> set[int]:
    result: set[int] = set()
    for filename in filenames:
        result.update(int(entry["id"]) for entry in load_entries(filename))
    return result


def validate_overrides(
    entries: list[dict], known_ids: set[int], allowed_fields: set[str], label: str
) -> None:
    seen: set[int] = set()
    for index, entry in enumerate(entries):
        entry_id = int(entry["id"])
        if entry_id in seen:
            raise AssertionError(f"{label} has duplicate id {entry_id}")
        seen.add(entry_id)
        if entry_id not in known_ids:
            raise AssertionError(f"{label} index {index} references unknown id {entry_id}")
        unexpected = set(entry) - allowed_fields
        if unexpected:
            raise AssertionError(
                f"{label} index {index} has unsupported fields: {sorted(unexpected)}"
            )


def require(source: str, text: str, description: str) -> None:
    if text not in source:
        raise AssertionError(f"Missing {description}: {text}")


def test_runtime_command_override() -> None:
    javac = shutil.which("javac")
    java = shutil.which("java")
    if javac is None or java is None:
        raise AssertionError("Java compiler/runtime are required")
    if not SERVER_CORE.is_file() or not SERVER_PLUGINS.is_file():
        raise AssertionError("Server jars are required; run ./scripts/build-server.sh first")

    harness_source = r'''
import com.openrsc.server.external.EntityHandler;
import com.openrsc.server.external.NPCDef;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import sun.misc.Unsafe;

public final class NpcCommandOverrideHarness {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static Throwable invokeFailure(Method apply, EntityHandler handler, String path)
            throws Exception {
        try {
            apply.invoke(handler, path);
            throw new AssertionError("Expected override failure for " + path);
        } catch (InvocationTargetException failure) {
            return failure.getCause();
        }
    }

    public static void main(String[] args) throws Exception {
        Field unsafeField = Unsafe.class.getDeclaredField("theUnsafe");
        unsafeField.setAccessible(true);
        Unsafe unsafe = (Unsafe) unsafeField.get(null);
        EntityHandler handler = (EntityHandler) unsafe.allocateInstance(EntityHandler.class);
        handler.npcs = new ArrayList<NPCDef>();
        for (int id = 0; id <= 3; id++) handler.npcs.add(null);
        NPCDef original = new NPCDef();
        original.command1 = "Inspect";
        handler.npcs.set(3, original);

        Method apply = EntityHandler.class.getDeclaredMethod(
            "applyOptionalNpcOverrides", String.class);
        apply.setAccessible(true);
        apply.invoke(handler, args[0]);
        check(handler.npcs.get(3) != original, "override must preserve copy-on-write staging");
        check("Inspect".equals(original.command1), "override must not mutate the source definition");
        check("Talk-to".equals(handler.npcs.get(3).command1), "command must map to command1");

        ArrayList<NPCDef> acceptedCatalog = handler.npcs;
        Throwable unknown = invokeFailure(apply, handler, args[1]);
        check(unknown instanceof IllegalStateException, "unknown field must fail startup");
        check(unknown.getCause() instanceof IllegalArgumentException,
            "unknown field must retain strict schema validation");
        check(unknown.getCause().getMessage().contains("Unexpected npc override field 'commmand'"),
            "unknown-field failure must identify the field");
        check(handler.npcs == acceptedCatalog, "unknown field must not swap the staged catalog");

        Throwable nonString = invokeFailure(apply, handler, args[2]);
        check(nonString instanceof IllegalStateException, "non-string command must fail startup");
        check(nonString.getCause() != null
                && nonString.getCause().getClass().getName().equals("org.json.JSONException"),
            "command must retain the provider's string contract");
        check(handler.npcs == acceptedCatalog, "invalid command must not swap the staged catalog");

        Method supplemental = EntityHandler.class.getDeclaredMethod(
            "supplementalNpcDefinitionFiles", Path.class);
        supplemental.setAccessible(true);
        @SuppressWarnings("unchecked")
        List<Path> catalogs = (List<Path>) supplemental.invoke(null, Paths.get(args[3]));
        check(catalogs.size() == 2, "only supplemental append catalogs must be discovered");
        check("AlphaNpcDefs.json".equals(catalogs.get(0).getFileName().toString()),
            "supplemental catalogs must use deterministic portable ordering");
        check("ZetaNpcDefs.json".equals(catalogs.get(1).getFileName().toString()),
            "supplemental catalogs must preserve every matching extension");

        Method sameContent = EntityHandler.class.getDeclaredMethod(
            "sameFileContent", Path.class, Path.class);
        sameContent.setAccessible(true);
        check((Boolean) sameContent.invoke(null,
                Paths.get(args[3], "AlphaNpcDefs.json"),
                Paths.get(args[3], "NpcDefs.json")),
            "legacy bundle copies must opt into target supplemental catalogs");
        check(!((Boolean) sameContent.invoke(null,
                Paths.get(args[3], "AlphaNpcDefs.json"),
                Paths.get(args[3], "ZetaNpcDefs.json"))),
            "merged project catalogs must not append target supplements twice");

        handler.npcs = new ArrayList<NPCDef>();
        for (int id = 0; id < 846; id++) handler.npcs.add(null);
        Method loadSupplemental = EntityHandler.class.getDeclaredMethod(
            "loadSupplementalNpcs", Path.class);
        loadSupplemental.setAccessible(true);
        loadSupplemental.invoke(handler, Paths.get(args[4]));
        check(handler.npcs.size() == 863,
            "supplemental catalogs must extend the registry through declared id 862");
        check("Gorak".equals(handler.npcs.get(861).name)
                && !handler.npcs.get(861).isAttackable(),
            "id 861 must come from the later-sorted visual catalog");
        check("Green Dragon".equals(handler.npcs.get(862).name)
                && handler.npcs.get(862).isAttackable(),
            "id 862 must retain its attackable definition from the earlier-sorted world catalog");
    }
}
'''
    classpath = os.pathsep.join((str(SERVER_CORE), str(SERVER_PLUGINS)))
    with tempfile.TemporaryDirectory(prefix="npc-command-override-") as temporary:
        temporary_path = Path(temporary)
        harness = temporary_path / "NpcCommandOverrideHarness.java"
        harness.write_text(harness_source, encoding="utf-8")
        supplemental = temporary_path / "defs"
        supplemental.mkdir()
        for name in (
            "NpcDefs.json", "NpcDefsCustom.json", "NpcDefsMyWorld.json",
            "NpcDefsPatch18.json", "ZetaNpcDefs.json", "AlphaNpcDefs.json",
        ):
            (supplemental / name).write_text("{}", encoding="utf-8")
        (supplemental / "ZetaNpcDefs.json").write_text('{"z":1}', encoding="utf-8")

        def npc_definition(npc_id: int, name: str, attackable: bool) -> dict:
            definition = {
                "id": npc_id,
                "name": name,
                "description": name,
                "command": "",
                "command2": "",
                "attack": 1,
                "strength": 1,
                "hits": 1,
                "defense": 1,
                "ranged": False,
                "combatlvl": 1,
                "isMembers": 0,
                "attackable": 1 if attackable else 0,
                "aggressive": 0,
                "respawnTime": 30,
                "hairColour": 0,
                "topColour": 0,
                "bottomColour": 0,
                "skinColour": 0,
                "camera1": 0,
                "camera2": 0,
                "walkModel": 0,
                "combatModel": 0,
                "combatSprite": 0,
                "roundMode": 0,
            }
            for sprite in range(1, 13):
                definition[f"sprites{sprite}"] = -1
            return definition

        declared_id_supplemental = temporary_path / "declared-id-defs"
        declared_id_supplemental.mkdir()
        monster_slayer = [
            npc_definition(npc_id, f"Monster Slayer {npc_id}", False)
            for npc_id in range(846, 861)
        ]
        (declared_id_supplemental / "MonsterSlayerNpcDefs.json").write_text(
            json.dumps({"npcs": monster_slayer}), encoding="utf-8"
        )
        (declared_id_supplemental / "MyWorldNpcDefs.json").write_text(
            json.dumps({"npcs": [npc_definition(862, "Green Dragon", True)]}),
            encoding="utf-8",
        )
        (declared_id_supplemental / "VisualTestNpcDefs.json").write_text(
            json.dumps({"npcs": [npc_definition(861, "Gorak", False)]}),
            encoding="utf-8",
        )
        compiled = subprocess.run(
            [
                javac,
                "-source", "8",
                "-target", "8",
                "-cp", classpath,
                "-d", str(temporary_path),
                str(ENTITY_HANDLER),
                str(harness),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if compiled.returncode != 0:
            raise AssertionError(f"NPC override harness compilation failed:\n{compiled.stderr}")
        executed = subprocess.run(
            [
                java,
                "-cp", os.pathsep.join((str(temporary_path), classpath)),
                "NpcCommandOverrideHarness",
                str(FIXTURES / "npc-command-override.json"),
                str(FIXTURES / "npc-unknown-field-override.json"),
                str(FIXTURES / "npc-non-string-command-override.json"),
                str(supplemental),
                str(declared_id_supplemental),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if executed.returncode != 0:
            raise AssertionError(
                "NPC override harness execution failed:\n"
                f"stdout:\n{executed.stdout}\nstderr:\n{executed.stderr}"
            )


def main() -> None:
    validate_overrides(
        load_entries("NpcDefsMyWorld.json"),
        definition_ids("NpcDefs.json", "NpcDefsCustom.json"),
        NPC_FIELDS,
        "NpcDefsMyWorld.json",
    )
    validate_overrides(
        load_entries("ItemDefsMyWorld.json"),
        definition_ids("ItemDefs.json", "ItemDefsCustom.json"),
        ITEM_FIELDS,
        "ItemDefsMyWorld.json",
    )

    command_override = json.loads(
        (FIXTURES / "npc-command-override.json").read_text(encoding="utf-8")
    )["npcs"]
    validate_overrides(command_override, {3}, NPC_FIELDS, "npc-command-override.json")
    if command_override[0]["command"] != "Talk-to":
        raise AssertionError("NPC command override fixture must exercise a string command")

    unknown_override = json.loads(
        (FIXTURES / "npc-unknown-field-override.json").read_text(encoding="utf-8")
    )["npcs"]
    try:
        validate_overrides(unknown_override, {3}, NPC_FIELDS, "npc-unknown-field-override.json")
    except AssertionError as failure:
        if "commmand" not in str(failure):
            raise
    else:
        raise AssertionError("unknown NPC override fields must remain rejected")

    source = ENTITY_HANDLER.read_text(encoding="utf-8")
    require(source, "ArrayList<NPCDef> stagedNpcs = new ArrayList<>(npcs);", "staged NPC catalog")
    require(source, "npcs = stagedNpcs;", "atomic NPC catalog swap")
    require(source, '"meleeOffense", "rangedOffense", "magicOffense"', "NPC power override whitelist")
    require(source, '"projectileRange"', "NPC projectile range override whitelist")
    require(source, '"id", "name", "description", "command"', "NPC command override whitelist")
    require(source, 'if (npc.has("command")) staged.command1 = npc.getString("command");', "NPC command override")
    require(source, 'if (npc.has("projectileRange"))', "NPC projectile range override")
    require(source, 'if (npc.has("meleeOffense")) staged.meleeOffense', "NPC melee power override")
    require(source, 'if (npc.has("rangedOffense")) staged.rangedOffense', "NPC ranged power override")
    require(source, 'if (npc.has("magicOffense")) staged.magicOffense', "NPC magic power override")
    require(source, "ArrayList<ItemDefinition> stagedItems = new ArrayList<>(items);", "staged item catalog")
    require(source, "items = stagedItems;", "atomic item catalog swap")
    require(source, 'throw new IllegalArgumentException("Duplicate npc override id "', "duplicate NPC rejection")
    require(source, 'validateOverrideFields(npc, MYWORLD_NPC_OVERRIDE_FIELDS, "npc", i);', "NPC unknown-field validation")
    require(source, '"Unexpected " + type + " override field \'" + field + "\' at index " + index', "unknown-field rejection")
    require(source, 'throw new IllegalArgumentException("Duplicate item override id "', "duplicate item rejection")
    require(source, 'throw new IllegalStateException("Failed to apply npc overrides from "', "NPC startup failure")
    require(source, 'throw new IllegalStateException("Failed to apply item overrides from "', "item startup failure")

    test_runtime_command_override()

    print("PASS: MyWorld definition overrides are validated and applied transactionally")


if __name__ == "__main__":
    main()

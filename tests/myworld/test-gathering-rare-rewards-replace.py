#!/usr/bin/env python3
import re
import sys
from pathlib import Path
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[2]
FISHING = ROOT / "server" / "plugins" / "com" / "openrsc" / "server" / "plugins" / "authentic" / "skills" / "fishing" / "Fishing.java"
MINING = ROOT / "server" / "plugins" / "com" / "openrsc" / "server" / "plugins" / "authentic" / "skills" / "mining" / "Mining.java"
WOODCUTTING = ROOT / "server" / "plugins" / "com" / "openrsc" / "server" / "plugins" / "authentic" / "skills" / "woodcutting" / "Woodcutting.java"


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}")
    sys.exit(1)


def require(snippet: str, text: str, label: str) -> None:
    if snippet not in text:
        fail(f"{label} missing expected snippet: {snippet}")


def require_regex(pattern: str, text: str, label: str) -> None:
    if not re.search(pattern, text, re.DOTALL):
        fail(f"{label} missing expected pattern: {pattern}")


def main() -> None:
    fishing = FISHING.read_text(encoding="utf-8")
    mining = MINING.read_text(encoding="utf-8")
    woodcutting = WOODCUTTING.read_text(encoding="utf-8")

    require("private boolean maybeAwardMyWorldFishingSpecialReward(Player player, int rodTier)", fishing, "Fishing rare replacement helper")
    require("boolean rareRewardAwarded = maybeAwardMyWorldFishingSpecialReward(player, rodTier);", fishing, "Fishing rare replacement roll")
    require_regex(
        r"boolean rareRewardAwarded = maybeAwardMyWorldFishingSpecialReward\(player, rodTier\);.*?"
        r"if \(!rareRewardAwarded\) \{.*?sendCatchMessage\(player, fish\);.*?awardFishingCatch\(player, object, fish, true\);.*?\}",
        fishing,
        "Fishing should only award the normal fish when no rare reward replaced it",
    )
    if "getCosmicAmuletExtraResourceChance" in fishing:
        fail("Fishing should use fisher amulet carryover instead of the old cosmic extra-resource chance")

    require("private boolean maybeAwardMyWorldMiningGeode(Player player, GameObject rock, int nodeRequiredLevel)", mining, "Mining rare replacement helper")
    require_regex(
        r"if \(maybeAwardMyWorldMiningGeode\(player, rock, def\.getReqLevel\(\)\)\) \{.*?"
        r"player\.incExp\(Skill\.MINING\.id\(\), def\.getExp\(\) \* quantity, true\);.*?"
        r"\} else \{.*?int rewardQuantity = publicBase \? quantity : quantity \+ addGatheringAmuletBonusOre\(player, ore\.getCatalogId\(\), quantity\);.*?"
        r"int bankedQuantity = publicBase \? 0 : player\.getCarriedItems\(\)\.getEquipment\(\)\.bankSkillingDropWithLawRing\(new Item\(ore\.getCatalogId\(\), rewardQuantity\)\)",
        mining,
        "Mining should award either the geode or the ore, not both",
    )

    require("private boolean maybeAwardMyWorldWoodcuttingSeed(Player player, GameObject object, int axeTier)", woodcutting, "Woodcutting rare replacement helper")
    require("boolean rareRewardAwarded = player.getConfig().WANT_MYWORLD && maybeAwardMyWorldWoodcuttingSeed(player, object, getAxeTier(axeId));", woodcutting, "Woodcutting rare replacement roll")
    require_regex(
        r"if \(!rareRewardAwarded\) \{.*?"
        r"int rewardQuantity = publicBase \? quantity : quantity \+ addGatheringAmuletBonusLogs\(player, def\.getLogId\(\), quantity\);.*?"
        r"int bankedQuantity = publicBase \? 0 : player\.getCarriedItems\(\)\.getEquipment\(\)\.bankSkillingDropWithLawRing\(new Item\(def\.getLogId\(\), rewardQuantity\)\)",
        woodcutting,
        "Woodcutting should only award logs and extra logs when no seed replaced them",
    )

    print("PASS: gathering rare rewards replace standard resources")


if __name__ == "__main__":
    main()

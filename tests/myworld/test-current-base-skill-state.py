#!/usr/bin/env python3
"""Actual packaged skill-load/setter regression; not a database or full public UI proof."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"

PROBE = r'''
import com.openrsc.server.CurrentCompositionIdentity;
import com.openrsc.server.Server;
import com.openrsc.server.constants.Skill;
import com.openrsc.server.database.struct.PlayerExperience;
import com.openrsc.server.database.struct.PlayerSkills;
import com.openrsc.server.model.Skills;
import com.openrsc.server.model.entity.player.Player;
import com.openrsc.server.model.entity.npc.Npc;
import com.openrsc.server.model.container.Item;
import com.openrsc.server.util.rsc.CombatEffectUtil;
import java.lang.reflect.*;
import java.util.*;

public final class PublicSkillStateProbe {
  static void check(boolean condition, String label) {
    if (!condition) throw new AssertionError(label);
  }
  static PlayerSkills level(int skill, int value) {
    PlayerSkills row = new PlayerSkills(); row.skillId = skill; row.skillLevel = value; return row;
  }
  static PlayerExperience xp(int skill, int value) {
    PlayerExperience row = new PlayerExperience(); row.skillId = skill; row.experience = value; return row;
  }
  public static void main(String[] args) {
    try { run(args[0].equals("base")); System.exit(0); }
    catch (Throwable failure) { failure.printStackTrace(); System.exit(1); }
  }
  static void run(boolean base) throws Exception {
    if (base) CurrentCompositionIdentity.initializeFromSystemProperties();
    Server server = new Server("current-base.conf");
    Player player = new Player(server.getWorld(), 725L);
    Skills skills = player.getSkills(); int fire = Skill.FIREMAKING.id();
    check(skills.getLevel(fire) == (base ? 1 : 99), "new-player policy");
    int hiddenXp = skills.getExperience(fire);
    // These are the actual entry points called by player database loading.
    skills.loadExp(new PlayerExperience[]{xp(fire, 765432)});
    skills.loadLevels(new PlayerSkills[]{level(fire, 37)});
    skills.loadMaxLevels(new PlayerSkills[]{level(fire, 44)});
    check(skills.getExperience(fire) == (base ? 765432 : hiddenXp), "loaded XP overwritten");
    check(skills.getLevel(fire) == (base ? 37 : 99), "loaded current level overwritten");
    check(skills.getMaxStat(fire) == (base ? 44 : 99), "loaded max level overwritten");
    skills.setExperienceAndLevel(fire, 345678, 33, false);
    check(skills.getExperience(fire) == (base ? 345678 : hiddenXp), "ordinary setter lost XP");
    skills.setLevel(fire, 21, false, true);
    check(skills.getLevel(fire) == (base ? 21 : 99), "temporary level overwritten");
    skills.setTemporaryLevelAndMaxStat(fire, 19, 33, false);
    check(skills.getLevel(fire) == (base ? 19 : 99), "temporary setter lost current level");
    check(skills.getMaxStat(fire) == (base ? 33 : 99), "temporary setter lost max level");
    check(skills.getExperience(fire) == (base ? 345678 : hiddenXp), "temporary setter changed XP");
    // Loading a different skill must not rewrite already loaded Firemaking.
    skills.loadLevels(new PlayerSkills[]{level(Skill.MINING.id(), 17)});
    check(skills.getLevel(fire) == (base ? 19 : 99), "unrelated load changed Firemaking");
    int rawTotal = 0;
    for (int i = 0; i < skills.getLevels().length; i++) rawTotal += skills.getMaxStat(i);
    check(skills.getTotalLevel() == rawTotal - (base ? 0 : 99), "raw total policy");
    check(server.getConstants().getSkills().getSkillsCount() == (base ? 18 : 20), "registry end bound");
    check(server.getConstants().getSkills().getSkillName(0).equals(base ? "Attack" : "Melee"), "numeric0 identity");
    check(server.getConstants().getSkills().getSkillDisplayName(5).equals(base ? "Prayer" : "Worship"), "prayer presentation");
    for (int style = 0; style < 4; style++) {
      player.setCombatStyle(style);
      check(player.combatStyleToIndex() == (base ? new int[]{-1,2,0,1}[style] : style == 0 ? -1 : 0), "style numeric identity");
    }
    for (int id = 0; id < 3; id++) check(CombatEffectUtil.remapLegacyPlayerMeleeStat(player, id) == (base ? id : 0), "buff identity");
    check(Arrays.equals(CombatEffectUtil.remapLegacyPlayerMeleeStats(player, 0,1,2), base ? new int[]{0,1,2} : new int[]{0}), "independent buff set");
    if (base) {
      server.getEntityHandler().load();
      player.setClientVersion(server.getConfig().CLIENT_VERSION);
      player.setClientLimitations(com.openrsc.server.net.rsc.ClientLimitations.forVersion(player.getClientVersion()));
      player.getClientLimitations().maxSkillId = 17;
      player.getClientLimitations().maxItemId = 1592;
      player.setLocation(com.openrsc.server.model.Point.location(120,648),true);
      for (int id = 0; id < 18; id++) skills.setExperienceAndLevel(id, 14000000,99,false);
      skills.setExperienceAndLevel(1, 14000000,19,false);
      check(!player.getCarriedItems().getEquipment().ableToEquip(new Item(130)), "Mithril shield must require Defense20 despite Attack99");
      skills.setExperienceAndLevel(1,14000000,20,false);
      skills.setExperienceAndLevel(0,14000000,1,false);
      check(player.getCarriedItems().getEquipment().ableToEquip(new Item(130)), "Mithril shield eligible with Defense20 and Attack1");
      skills.setExperienceAndLevel(4,14000000,15,false);
      skills.setExperienceAndLevel(0,14000000,19,false);
      check(!player.getCarriedItems().getEquipment().ableToEquip(new Item(1090)), "Mithril spear secondary Attack20");
      skills.setExperienceAndLevel(0,14000000,20,false);
      check(player.getCarriedItems().getEquipment().ableToEquip(new Item(1090)), "Mithril spear dual skills satisfied");
      for (int id = 0; id < 18; id++) skills.setExperienceAndLevel(id,14000000,99,false);
      Npc npc = new Npc(server.getWorld(),3,120,648);
      Method melee = Npc.class.getDeclaredMethod("awardMeleeDamageShareXp",Player.class,int.class,int.class); melee.setAccessible(true);
      Method range = Npc.class.getDeclaredMethod("awardRangedDamageShareXp",Player.class,int.class,int.class); range.setAccessible(true);
      Method magic = Npc.class.getDeclaredMethod("awardMagicDamageShareXp",Player.class,int.class,int.class); magic.setAccessible(true);
      int[][] weights = {{1,1,1,1},{0,0,3,1},{3,0,0,1},{0,3,0,1}};
      for (int style = 0; style < 4; style++) for (int focus = 0; focus < 4; focus++) {
        player.setCombatStyle(style); player.setHitsXpFocus(focus);
        int[] before = skills.getExperiences().clone();
        melee.invoke(npc,player,npc.getDef().hits,23);
        for (int id = 0; id < 18; id++) check(skills.getExperience(id)-before[id] == (id < 4 ? weights[style][id]*23 : 0), "actual melee XP style/focus/id="+style+"/"+focus+"/"+id);
      }
      int[] before = skills.getExperiences().clone();
      range.invoke(npc,player,npc.getDef().hits,23);
      int rangedExpected = 92-(server.getConfig().RANGED_GIVES_XP_HIT ? 16*npc.getDef().hits/3 : 0);
      for (int id=0; id<18;id++) check(skills.getExperience(id)-before[id] == (id==4 ? Math.max(0,rangedExpected) : 0), "actual ranged remainder identity");
      before=skills.getExperiences().clone(); magic.invoke(npc,player,npc.getDef().hits,23);
      check(Arrays.equals(before,skills.getExperiences()),"magic death must not double award cast XP");
    }
    System.out.println("SKILL_STATE_VERIFIED " + (base ? "base" : "unselected-control"));
  }
}
'''


class PublicSkillStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('CURRENT_BASE_PUBLIC_USE_EXISTING') == '1':
            return
        build = subprocess.run(["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
                               cwd=ROOT, capture_output=True, text=True, timeout=240)
        if build.returncode:
            raise AssertionError(build.stdout[-12000:] + build.stderr[-12000:])

    def probe(self, mode):
        with tempfile.TemporaryDirectory(prefix="current-base-skill-state-") as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(OUTPUT / "server/content.zip") as archive:
                archive.extractall(root)
            source = root / "PublicSkillStateProbe.java"
            source.write_text(PROBE, encoding="utf-8")
            jars = os.pathsep.join(str(OUTPUT / "server" / name) for name in ("core.jar", "plugins.jar"))
            compiled = subprocess.run(["javac", "-cp", jars, "-d", str(root), str(source)],
                                      cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            command = ["java", "-Djava.awt.headless=true"]
            if mode == "base":
                command.append("-Dopenrsc.currentCompositionIdentityFile=" + str(OUTPUT / "composition-identity.json"))
            command += ["-cp", str(root) + os.pathsep + jars, "PublicSkillStateProbe", mode]
            # The unselected control deliberately does not initialize a composition;
            # it is a Skills regression, not a claim of launching an Advanced server.
            environment = {key: value for key, value in os.environ.items()
                           if not key.startswith(("OPENRSC_", "SPOILED_MILK_"))
                           and key not in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH")}
            result = subprocess.run(command, cwd=root, env=environment,
                                    capture_output=True, text=True, timeout=40)
            self.assertEqual(0, result.returncode, result.stdout[-6000:] + result.stderr[-12000:])
            self.assertIn("SKILL_STATE_VERIFIED", result.stdout)

    def test_public_loaded_firemaking_and_mutators_preserve_state(self):
        self.probe("base")

    def test_unselected_runtime_retains_hidden_firemaking_policy(self):
        self.probe("unselected")


if __name__ == "__main__":
    unittest.main()

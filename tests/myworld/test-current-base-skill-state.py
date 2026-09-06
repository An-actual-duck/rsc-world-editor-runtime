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
    System.out.println("SKILL_STATE_VERIFIED " + (base ? "base" : "unselected-control"));
  }
}
'''


class PublicSkillStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

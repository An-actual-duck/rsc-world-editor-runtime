#!/usr/bin/env python3
"""Actual packaged skill state, SQLite, XP dispatch and protocol regression; no GUI/full combat claim."""
import os
from pathlib import Path
import subprocess
import tempfile
import sqlite3
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
    try {
      if(args[0].equals("non-base-selection")) {
        // Selection-unit seam only: no claim that this is a valid Advanced artifact launch.
        Constructor<CurrentCompositionIdentity> constructor=CurrentCompositionIdentity.class.getDeclaredConstructor(boolean.class,Map.class);constructor.setAccessible(true);
        Map<String,String> fields=new HashMap<>();fields.put("variantId","current-advanced-v1");
        Field current=CurrentCompositionIdentity.class.getDeclaredField("current");current.setAccessible(true);current.set(null,constructor.newInstance(true,fields));
      }
      run(args[0].equals("base")); System.exit(0);
    }
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
      for(int[] requirement:new int[][]{{1078,4,15,20},{615,6,30,30},{1000,6,50,50}}) {
        skills.setExperienceAndLevel(requirement[1],14000000,requirement[2],false);
        skills.setExperienceAndLevel(0,14000000,requirement[3]-1,false);
        check(!player.getCarriedItems().getEquipment().ableToEquip(new Item(requirement[0])),"knife/staff insufficient Attack "+requirement[0]);
        skills.setExperienceAndLevel(0,14000000,requirement[3],false);
        check(player.getCarriedItems().getEquipment().ableToEquip(new Item(requirement[0])),"knife/staff exact secondary Attack "+requirement[0]);
      }
      // Actual stock NPC weakening dispatch must drain each independent stat.
      for(int id=0;id<3;id++) skills.setExperienceAndLevel(id,14000000,40+10*id,false);
      Npc skeleton=new Npc(server.getWorld(),com.openrsc.server.constants.NpcId.SKELETON_MAGE.id(),120,648);
      com.openrsc.server.event.rsc.impl.combat.scripts.all.SkeletonMage weakening=new com.openrsc.server.event.rsc.impl.combat.scripts.all.SkeletonMage();
      check(weakening.shouldExecute(skeleton,player),"actual public weakening eligibility");weakening.executeScript(skeleton,player);
      for(int id=0;id<3;id++) check(skills.getLevel(id)==40+10*id-(int)Math.ceil((60+10*id)*0.05),"independent effective weakening "+id);
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
      // Truncate the damage share before applying the style weights, as in the public source.
      for (int damage=1;damage<npc.getDef().hits;damage++) for(int style=0;style<4;style++) {
        player.setCombatStyle(style);
        int[] prior=skills.getExperiences().clone();
        melee.invoke(npc,player,damage,23);
        int share=(int)((23.0/npc.getDef().hits)*damage);
        for(int id=0;id<18;id++) check(skills.getExperience(id)-prior[id]==(id<4?weights[style][id]*share:0),"partial damage truncation");
      }
      // Invoke the real PvP death dispatch. The disposable victim is not logged in,
      // so killedBy's existing guard avoids inventory/death-world side effects.
      Player victim=new Player(server.getWorld(),729L);
      Field duel=Player.class.getDeclaredField("duel");duel.setAccessible(true);
      duel.set(player,new com.openrsc.server.model.entity.player.Duel(player));
      duel.set(victim,new com.openrsc.server.model.entity.player.Duel(victim));
      com.openrsc.server.util.PidShuffler.pidProcessingOrder=new int[0];
      com.openrsc.server.event.rsc.impl.combat.CombatEvent combat=new com.openrsc.server.event.rsc.impl.combat.CombatEvent(server.getWorld(),player,victim);
      Method death=combat.getClass().getDeclaredMethod("onDeath",com.openrsc.server.model.entity.Mob.class,com.openrsc.server.model.entity.Mob.class); death.setAccessible(true);
      int pvpXp=com.openrsc.server.util.rsc.Formulae.combatExperience(victim);
      for(int style=0;style<4;style++) {
        player.setCombatStyle(style);int[] prior=skills.getExperiences().clone();death.invoke(combat,victim,player);
        for(int id=0;id<18;id++) check(skills.getExperience(id)-prior[id]==(id<4?weights[style][id]*pvpXp:0),"actual PvP onDeath style"+style);
      }
      double oldCombatRate=server.getConfig().COMBAT_EXP_RATE,oldSkillRate=server.getConfig().SKILLING_EXP_RATE;
      server.getConfig().COMBAT_EXP_RATE=2.5;server.getConfig().SKILLING_EXP_RATE=3.0;
      for(int id:new int[]{0,1,2,6,11}) {
        int prior=skills.getExperience(id);player.incExp(id,20,false);
        check(skills.getExperience(id)-prior==(id==11?60:50),"public configured XP rate "+id);
      }
      server.getConfig().COMBAT_EXP_RATE=oldCombatRate;server.getConfig().SKILLING_EXP_RATE=oldSkillRate;
      int[] before = skills.getExperiences().clone();
      range.invoke(npc,player,npc.getDef().hits,23);
      int rangedExpected = 92-(server.getConfig().RANGED_GIVES_XP_HIT ? 16*npc.getDef().hits/3 : 0);
      for (int id=0; id<18;id++) check(skills.getExperience(id)-before[id] == (id==4 ? Math.max(0,rangedExpected) : 0), "actual ranged remainder identity");
      before=skills.getExperiences().clone(); magic.invoke(npc,player,npc.getDef().hits,23);
      check(Arrays.equals(before,skills.getExperiences()),"magic death must not double award cast XP");
      before=skills.getExperiences().clone();
      com.openrsc.server.net.rsc.handlers.SpellHandler.finalizeSpell(player,server.getEntityHandler().getSpellDef(0),null);
      check(skills.getExperience(6)-before[6]==88,"public Wind Strike cast XP");
      // Real SQLite save/load methods, independent current/max/XP and a reopened connection.
      com.openrsc.server.database.impl.sqlite.SqliteGameDatabase database = new com.openrsc.server.database.impl.sqlite.SqliteGameDatabase(server);
      check(database.getConnection().open(),"private external SQLite open");
      StringBuilder columns=new StringBuilder("playerID INTEGER PRIMARY KEY");
      for (int id=0;id<18;id++) columns.append(",`").append(server.getConstants().getSkills().getSkillName(id).toLowerCase()).append("` INTEGER NOT NULL DEFAULT 0");
      columns.append(",preserved_extra INTEGER NOT NULL DEFAULT 777");
      for(String table:new String[]{"experience","curstats","maxstats"}) {
        database.getConnection().executeUpdate("CREATE TABLE `"+server.getConfig().DB_TABLE_PREFIX+table+"` ("+columns+")");
        database.getConnection().executeUpdate("INSERT INTO `"+server.getConfig().DB_TABLE_PREFIX+table+"`(playerID) VALUES(725)");
      }
      int[] ids={0,1,2,11}, current={47,19,66,12}, max={40,31,60,25}, experience={123456,234568,345680,456792};
      player.setDatabaseID(725);
      for(int i=0;i<ids.length;i++) {
        skills.setExperienceAndLevel(ids[i],experience[i],max[i],false);
        skills.setTemporaryLevelAndMaxStat(ids[i],current[i],max[i],false);
      }
      player.setAttribute("giant_might_melee_bonus",9);
      for(int i=0;i<ids.length;i++) {
        check(player.getPersistedSkillLevel(ids[i])==current[i],"no owner state stripping");
        check(player.getEquipmentAdjustedNormalLevel(ids[i])==max[i],"independent normalization max");
      }
      database.querySavePlayerExperience(player);database.querySavePlayerSkills(player);database.querySavePlayerMaxSkills(player);
      database.getConnection().close();check(database.getConnection().open(),"SQLite reconnect");
      Player reloaded=new Player(server.getWorld(),726L);reloaded.setDatabaseID(725);
      reloaded.getSkills().loadExp(database.queryLoadPlayerExperience(725));
      reloaded.getSkills().loadLevels(database.queryLoadPlayerSkills(reloaded,false));
      reloaded.getSkills().loadMaxLevels(database.queryLoadPlayerSkills(reloaded,true));
      for(int i=0;i<ids.length;i++) {
        check(reloaded.getSkills().getLevel(ids[i])==current[i],"SQLite current preserved"+ids[i]);
        check(reloaded.getSkills().getMaxStat(ids[i])==max[i],"SQLite max preserved"+ids[i]);
        check(reloaded.getSkills().getExperience(ids[i])==experience[i],"SQLite XP preserved"+ids[i]);
      }
      for(String table:new String[]{"experience","curstats","maxstats"})
        try(java.sql.ResultSet row=database.getConnection().executeQuery("SELECT preserved_extra FROM `"+server.getConfig().DB_TABLE_PREFIX+table+"` WHERE playerID=725")) {
          check(row.next() && row.getInt(1)==777,"unselected state columns untouched");
        }
      database.getConnection().close();
    }
    // Actual ActionSender -> selected generator -> Player outbound queue, no socket.
    player.setClientVersion(server.getConfig().CLIENT_VERSION);
    player.setClientLimitations(com.openrsc.server.net.rsc.ClientLimitations.forVersion(player.getClientVersion()));
    player.getClientLimitations().maxSkillId=base?17:19;
    io.netty.channel.embedded.EmbeddedChannel channel=new io.netty.channel.embedded.EmbeddedChannel();
    Field channelField=Player.class.getDeclaredField("channel");channelField.setAccessible(true);channelField.set(player,channel);
    Field loggedIn=Player.class.getDeclaredField("loggedIn");loggedIn.setAccessible(true);loggedIn.setBoolean(player,true);
    Field outgoing=Player.class.getDeclaredField("outgoingPackets");outgoing.setAccessible(true);
    java.util.List<com.openrsc.server.net.Packet> packets=(java.util.List<com.openrsc.server.net.Packet>)outgoing.get(player);
    com.openrsc.server.net.rsc.ActionSender.sendStats(player);
    check(packets.size()==1,"actual full stats emitted");
    io.netty.buffer.ByteBuf payload=packets.remove(0).getBuffer();
    int count=base?18:20;
    check(payload.readableBytes()==count*6+1,"exact stats packet width "+payload.readableBytes());
    for(int id=0;id<count;id++) check(payload.readUnsignedByte()==skills.getLevel(id),"packet current numeric identity "+id);
    for(int id=0;id<count;id++) check(payload.readUnsignedByte()==skills.getMaxStat(id),"packet max numeric identity "+id);
    for(int id=0;id<count;id++) check(payload.readInt()==skills.getExperience(id),"packet XP numeric identity "+id);
    check(payload.readUnsignedByte()==player.getQuestPoints(),"quest points position");payload.release();
    for(int id:new int[]{0,1,2,11}) {
      com.openrsc.server.net.rsc.ActionSender.sendStat(player,id);
      check(packets.size()==1,"actual stat update emitted");payload=packets.remove(0).getBuffer();
      check(payload.readableBytes()==7&&payload.readUnsignedByte()==id&&payload.readUnsignedByte()==skills.getLevel(id)&&payload.readUnsignedByte()==skills.getMaxStat(id)&&payload.readInt()==skills.getExperience(id),"single stat identity "+id);payload.release();
      com.openrsc.server.net.rsc.ActionSender.sendExperience(player,id);
      check(packets.size()==1,"actual XP update emitted");payload=packets.remove(0).getBuffer();
      check(payload.readableBytes()==5&&payload.readUnsignedByte()==id&&payload.readInt()==skills.getExperience(id),"single XP identity "+id);payload.release();
    }
    loggedIn.setBoolean(player,false);channel.finishAndReleaseAll();
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
        with tempfile.TemporaryDirectory(prefix="current-base-skill-state-") as temporary, \
             tempfile.TemporaryDirectory(prefix="current-base-skill-external-") as external_state:
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
                database = Path(external_state) / 'current_base.db'
                sqlite3.connect(database).close()
                database.chmod(0o600)
                command.append('-Dopenrsc.currentBaseStateRoot=' + external_state)
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

    def test_enabled_non_base_selection_retains_existing_skill_policy(self):
        self.probe("non-base-selection")


if __name__ == "__main__":
    unittest.main()

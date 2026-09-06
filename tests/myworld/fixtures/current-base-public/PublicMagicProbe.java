import com.openrsc.server.CurrentCompositionIdentity;
import com.openrsc.server.Server;
import com.openrsc.server.constants.*;
import com.openrsc.server.external.SpellDef;
import com.openrsc.server.model.Point;
import com.openrsc.server.model.container.Item;
import com.openrsc.server.model.entity.GameObject;
import com.openrsc.server.model.entity.player.Player;
import com.openrsc.server.net.rsc.handlers.SpellHandler;
import com.openrsc.server.plugins.SpellFailureException;
import com.openrsc.server.plugins.authentic.minigames.mage_arena.MageArena;
import java.lang.reflect.Method;
import java.util.*;

/** Actual packaged magic handlers and inventory mutation; no socket or database is opened. */
public final class PublicMagicProbe {
  static Server server;
  static Player player;
  static void check(boolean yes, String why) { if (!yes) throw new AssertionError(why); }
  static int count(int id) { return player.getCarriedItems().getInventory().countId(id); }
  static void clear() { player.getCarriedItems().getInventory().getItems().clear(); }
  static void add(int id, int amount) {
    check(player.getCarriedItems().getInventory().add(new Item(id, amount), false), "inventory add " + id);
  }
  static GameObject object(int id) { return new GameObject(server.getWorld(), Point.location(120, 648), id, 0, 0); }
  public static void main(String[] args) {
    try { run(); System.exit(0); } catch (Throwable failure) { failure.printStackTrace(); System.exit(1); }
  }
  static void run() throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    server = new Server("current-base.conf"); server.getEntityHandler().load();
    player = new Player(server.getWorld(), 725L);
    player.setClientVersion(server.getConfig().CLIENT_VERSION);
    player.setClientLimitations(com.openrsc.server.net.rsc.ClientLimitations.forVersion(player.getClientVersion()));
    // The custom client advertises these loaded-registry bounds during login;
    // forVersion alone only fills historical hard-coded protocol profiles.
    player.getClientLimitations().maxItemId = 1592;
    player.getClientLimitations().maxSkillId = 20;
    player.setLocation(Point.location(120, 648), true);
    player.setBank(new com.openrsc.server.model.container.Bank(player));
    server.getWorld().getPlayers().add(player);
    player.getSkills().setExperienceAndLevel(Skill.MAGIC.id(), 14000000, 99, false);
    int[][] staves = {{101, 617, 684}, {102, 616, 683}, {103, 618, 685}, {197, 615, 682}};
    // IDs are checked against loaded public names as well as actual spell results.
    int[] runes = {33, 32, 34, 31};
    Spells[] strikes = {Spells.WIND_STRIKE, Spells.WATER_STRIKE, Spells.EARTH_STRIKE, Spells.FIRE_STRIKE};
    String[] elements = {"air", "water", "earth", "fire"};
    int staffChecks = 0;
    for (int element = 0; element < staves.length; element++) for (int staffId : staves[element]) {
      check(server.getEntityHandler().getItemDef(staffId).getName().toLowerCase().contains(elements[element]), "stock staff fixture " + staffId);
      clear(); add(staffId, 1);
      Item staff = player.getCarriedItems().getInventory().get(0);
      SpellDef spell = server.getEntityHandler().getSpellDef(strikes[element]);
      for (Map.Entry<Integer, Integer> rune : spell.getRunesRequired()) if (rune.getKey() != runes[element]) add(rune.getKey(), rune.getValue() * 2);
      check(!SpellHandler.hasRequiredRunesForAutoCast(player, spell), "unwielded staff supplied runes");
      staff.getItemStatus().setWielded(true);
      check(SpellHandler.hasRequiredRunesForAutoCast(player, spell), "wielded public staff not accepted");
      Set<Map.Entry<Integer, Integer>> consumed = SpellHandler.checkSpellRunes(player, spell, false);
      for (Map.Entry<Integer, Integer> rune : consumed) check(rune.getKey() != runes[element], "matching rune consumed");
      check(SpellHandler.checkAndRemoveRunes(player, spell, false), "actual rune consumption failed");
      check(count(runes[element]) == 0 && count(staffId) == 1, "staff was not unlimited");
      for (Map.Entry<Integer, Integer> rune : spell.getRunesRequired()) if (rune.getKey() != runes[element])
        check(count(rune.getKey()) == rune.getValue(), "nonmatching rune cost changed");
      // Missing non-elemental reagents must still fail even with a matching staff.
      for (Iterator<Item> it = player.getCarriedItems().getInventory().getItems().iterator(); it.hasNext();)
        if (it.next().getCatalogId() != staffId) it.remove();
      check(!SpellHandler.hasRequiredRunesForAutoCast(player, spell), "staff supplied non-elemental runes");
      try { SpellHandler.checkSpellRunes(player, spell, false); throw new AssertionError("missing rune accepted"); }
      catch (SpellFailureException expected) { }
      staffChecks++;
    }
    Method charge = SpellHandler.class.getDeclaredMethod("handleChargeOrb", Player.class, GameObject.class, Spells.class, SpellDef.class);
    charge.setAccessible(true);
    Spells[] charges = {Spells.CHARGE_AIR_ORB, Spells.CHARGE_WATER_ORB, Spells.CHARGE_EARTH_ORB, Spells.CHARGE_FIRE_ORB};
    int[] obelisks = {303, 300, 304, 301};
    int[] orbs = {626, 613, 627, 612};
    for (int i = 0; i < charges.length; i++) {
      clear(); SpellDef spell = server.getEntityHandler().getSpellDef(charges[i]);
      for (Map.Entry<Integer, Integer> rune : spell.getRunesRequired()) add(rune.getKey(), rune.getValue());
      int beforeXp = player.getSkills().getExperience(Skill.MAGIC.id());
      charge.invoke(new SpellHandler(), player, object(2), charges[i], spell);
      check(count(611) == 1 && count(orbs[i]) == 0, "wrong obelisk mutated orb");
      check(player.getSkills().getExperience(Skill.MAGIC.id()) == beforeXp, "wrong obelisk granted XP");
      charge.invoke(new SpellHandler(), player, object(obelisks[i]), charges[i], spell);
      check(count(611) == 0 && count(orbs[i]) == 1, "orb replacement " + charges[i]);
      for (Map.Entry<Integer, Integer> rune : spell.getRunesRequired()) check(count(rune.getKey()) == 0, "orb reagent not consumed");
      check(player.getSkills().getExperience(Skill.MAGIC.id()) > beforeXp && player.lastCast > 0, "orb cast XP/timer");
      charge.invoke(new SpellHandler(), player, object(obelisks[i]), charges[i], spell);
      check(count(orbs[i]) == 1, "orb cast without reagents duplicated output");
    }
    MageArena arena = new MageArena(); server.getWorld().getMiniGames().add(arena);
    int[] capes = {1214, 1215, 1213};
    for (int i = 0; i < capes.length; i++) {
      clear(); player.getCache().set("mage_arena", 1);
      GameObject stone = object(1152 + i);
      check(arena.blockOpLoc(player, stone, "chant"), "stock stone not dispatched");
      arena.onOpLoc(player, stone, "chant"); check(count(capes[i]) == 0, "unearned cape");
      player.getCache().set("mage_arena", 2);
      arena.onOpLoc(player, stone, "chant");
      check(count(capes[i]) == 1 && player.getCache().getInt("mage_arena") == 3, "public cape/stage reward " + i);
      check(!player.getCache().hasKey("mage_arena_staff_reward"), "owner path reward enabled");
      arena.onOpLoc(player, object(1152 + (i + 1) % 3), "chant");
      check(player.getCarriedItems().getInventory().size() == 1, "multiple god capes permitted");
      clear(); player.getCache().set("mage_arena", 4);
      arena.onOpLoc(player, stone, "chant");
      check(count(capes[i]) == 1 && player.getCache().getInt("mage_arena") == 4, "replacement cape changed progression");
      clear(); player.getBank().getItems().add(new Item(capes[i]));
      arena.onOpLoc(player, stone, "chant");
      check(player.getCarriedItems().getInventory().size() == 0, "bank-owned cape did not prevent reward");
      player.getBank().getItems().clear();
      player.getCache().set("mage_arena", 2);
      for (int slot = 0; slot < 30; slot++) add(611, 1);
      arena.onOpLoc(player, stone, "chant");
      check(count(capes[i]) == 0 && count(611) == 30 && player.getCache().getInt("mage_arena") == 2,
        "full inventory stone changed items or progression");
    }
    System.out.println("PUBLIC_MAGIC_VERIFIED staffDispatch=" + staffChecks + " orbDispatch=4 stoneDispatch=3");
  }
}

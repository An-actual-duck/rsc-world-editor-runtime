import com.openrsc.server.CurrentCompositionIdentity;
import com.openrsc.server.CurrentBasePublicContent;
import com.openrsc.server.Server;
import com.openrsc.server.constants.Skill;
import com.openrsc.server.model.entity.player.Player;
import com.openrsc.server.model.container.Item;
import com.openrsc.server.external.ObjectWoodcuttingDef;
import com.openrsc.server.plugins.authentic.skills.mining.Mining;
import com.openrsc.server.plugins.authentic.skills.woodcutting.Woodcutting;
import com.openrsc.server.util.rsc.Formulae;
import java.lang.reflect.*;
import java.util.Map;

/** Real public inventory and public skill-dispatch checks against packaged jars. */
public final class PublicGatheringProbe {
  static void check(boolean yes, String why) { if (!yes) throw new AssertionError(why); }
  public static void main(String[] args) {
    try { run(); System.exit(0); } catch (Throwable failure) { failure.printStackTrace(); System.exit(1); }
  }
  static void run() throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    Server server = new Server("current-base.conf"); server.getEntityHandler().load();
    check(!server.getConfig().WANT_MYWORLD && !server.getConfig().WANT_EQUIPMENT_TAB
      && !server.getConfig().WANT_CUSTOM_SPRITES && !server.getConfig().WANT_HARVESTING
      && !server.getConfig().WANT_RUNECRAFT, "Advanced flags active");
    Player player = new Player(server.getWorld(), 725L);
    player.setClientVersion(server.getConfig().CLIENT_VERSION);
    int[] picks = {156, 1258, 1259, 1260, 1261, 1262};
    int[] levels = {1, 1, 6, 21, 31, 41};
    int[] repeats = {1, 2, 3, 5, 8, 12};
    int[] bonuses = {0, 1, 2, 4, 8, 16};
    check(Mining.getAxe(player) == -1, "empty inventory has pickaxe");
    for (int i = 0; i < picks.length; i++) {
      Item item = new Item(picks[i], 1);
      // Seed a loaded inventory without a login/database allocation; selection still
      // traverses the real CarriedItems/Inventory objects used by both plugins.
      player.getCarriedItems().getInventory().getItems().add(item);
      player.getSkills().setLevel(Skill.MINING.id(), levels[i] - 1, false, true);
      check(Mining.getAxe(player) == -1, "underlevel stock pickaxe accepted " + picks[i]);
      player.getSkills().setLevel(Skill.MINING.id(), levels[i], false, true);
      check(Mining.getAxe(player) == picks[i], "public inventory pickaxe not selected " + picks[i]);
      check(!player.getCarriedItems().getEquipment().hasCatalogID(picks[i]), "fixture unexpectedly equipped pickaxe");
      check(Mining.getPickaxeRequiredLevel(picks[i]) == levels[i], "public pickaxe level");
      check(Mining.getPickaxeRepeat(picks[i]) == repeats[i], "public pickaxe repeats");
      check(CurrentBasePublicContent.pickaxeBonus(picks[i]) == bonuses[i], "public pickaxe bonus");
      player.getCarriedItems().getInventory().getItems().clear();
    }
    int[] axes = {87, 12, 88, 428, 203, 204, 405, 1480};
    String[] curves = {"Bronze", "Iron", "Steel", "Black", "Mithril", "Adamantite", "Rune", "Dragon"};
    player.getSkills().setLevel(Skill.WOODCUTTING.id(), 1, false, true);
    for (int axe : axes) {
      Item item = new Item(axe, 1);
      player.getCarriedItems().getInventory().getItems().add(item);
      check(Woodcutting.getAxe(player) == axe, "public inventory axe not selected " + axe);
      check(!player.getCarriedItems().getEquipment().hasCatalogID(axe), "fixture unexpectedly equipped axe");
      player.getCarriedItems().getInventory().getItems().clear();
    }
    Field field = server.getEntityHandler().getClass().getDeclaredField("objectWoodcutting"); field.setAccessible(true);
    Map<?, ?> trees = (Map<?, ?>) field.get(server.getEntityHandler());
    check(trees.size() == 8, "public tree hook count");
    int curveChecks = 0;
    for (Object value : trees.values()) {
      ObjectWoodcuttingDef tree = (ObjectWoodcuttingDef) value;
      for (int i = 0; i < axes.length; i++) {
        Field curveField = tree.getClass().getDeclaredField("rate" + curves[i]); curveField.setAccessible(true);
        double[] curve = (double[]) curveField.get(tree);
        for (int level = 0; level <= 99; level++) {
          check(tree.getRate(level, axes[i]) == curve[level], "wrong stock axe curve " + axes[i]); curveChecks++;
        }
      }
    }
    for (int required = 1; required <= 99; required++) {
      for (int level = 0; level <= 99; level++) {
        for (int bonus : bonuses) {
          int threshold = Math.min(127, Math.max(1, level + bonus + 40 - (int) (required * 1.5)));
          check(Formulae.calcGatheringSuccessfulLegacy(required, level, bonus, threshold) == (level >= required), "public success threshold");
          check(!Formulae.calcGatheringSuccessfulLegacy(required, level, bonus, threshold + 1), "public failure threshold");
        }
      }
    }
    for (Object plugin : new Object[]{new Mining(), new Woodcutting()}) {
      Method timing = plugin.getClass().getDeclaredMethod("resourceRespawnMillis", int.class); timing.setAccessible(true);
      check(((Integer) timing.invoke(plugin, 40)) == 40000, "public respawn timing");
    }
    System.out.println("PUBLIC_GATHERING_VERIFIED inventoryTools=14 stockCurveChecks=" + curveChecks + " probabilityBoundaryChecks=118800");
  }
}

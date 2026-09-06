import com.openrsc.server.CurrentBasePublicContent;
import com.openrsc.server.constants.Constants;
import com.openrsc.server.constants.Spells;
import com.openrsc.server.external.ObjectWoodcuttingDef;
import java.lang.reflect.Field;
import java.util.Arrays;

/** Disabled-composition control; does not claim to launch an Advanced artifact. */
public final class PublicGenericDispatchProbe {
  public static void main(String[] args) throws Exception {
    if (CurrentBasePublicContent.isEnabled() || Constants.currentSpellMap() != Constants.spellMap
        || Constants.spellToEnum(1) != Spells.WATER_STRIKE || Constants.spellToEnum(4) != Spells.THUNDER_BALL)
      throw new AssertionError("public spell mapping leaked into unselected runtime");
    ObjectWoodcuttingDef tree = new ObjectWoodcuttingDef();
    for (String name : new String[]{"Bronze", "Iron", "Steel", "Black", "Mithril", "Adamantite", "Rune", "Dragon"}) {
      Field field = tree.getClass().getDeclaredField("rate" + name); field.setAccessible(true);
      double[] values = new double[100]; Arrays.fill(values, name.equals("Steel") ? 23.0 : 7.0); field.set(tree, values);
    }
    if (tree.getRate(50, 87) != 23.0) throw new AssertionError("public stock axe dispatch leaked into generic runtime");
    System.out.println("PUBLIC_GENERIC_CONTROL_VERIFIED");
  }
}

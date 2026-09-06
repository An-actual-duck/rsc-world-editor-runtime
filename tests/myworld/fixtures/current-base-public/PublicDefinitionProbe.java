import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import org.json.*;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;

/** Test-only probe of actual packaged loaders, not a substitute definition loader. */
public final class PublicDefinitionProbe {
  static final List<String> errors = new ArrayList<>();
  static int comparisons;
  static boolean client;
  static Object handler;
  static Class<?> handlerClass;
  static Path definitions;
  static Object server;

  static Object field(Object object, String name) throws Exception {
    for (Class<?> type = object.getClass(); type != null; type = type.getSuperclass()) {
      try {
        Field f = type.getDeclaredField(name); f.setAccessible(true); return f.get(object);
      } catch (NoSuchFieldException ignored) { }
    }
    throw new NoSuchFieldException(object.getClass().getName() + "." + name);
  }

  static Map<String, String> mapping(String... pairs) {
    Map<String, String> result = new HashMap<>();
    for (int i = 0; i < pairs.length; i += 2) result.put(pairs[i], pairs[i + 1]);
    return result;
  }

  static Set<String> skip(String... keys) { return new HashSet<>(Arrays.asList(keys)); }

  static void compare(Object actual, JSONObject expected, String label,
      Map<String, String> names, Set<String> omitted) throws Exception {
    if (actual == null) throw new AssertionError("missing " + label);
    for (String key : expected.keySet()) {
      if (omitted.contains(key)) continue;
      Object want = expected.get(key), got;
      if (key.startsWith("sprites") && key.length() > 7) {
        got = ((int[]) field(actual, "sprites"))[Integer.parseInt(key.substring(7)) - 1];
      } else {
        got = field(actual, names.getOrDefault(key, key));
      }
      if (got instanceof String[]) got = String.join(",", (String[]) got);
      if (got == null && "".equals(want)) got = "";
      if (got instanceof Boolean && want instanceof Number) want = ((Number) want).intValue() == 1;
      if (got instanceof Number && want instanceof Boolean) want = Boolean.TRUE.equals(want) ? 1 : 0;
      comparisons++;
      if (!String.valueOf(want).equals(String.valueOf(got)) && errors.size() < 30) {
        errors.add(label + "." + key + " expected=" + want + " actual=" + got);
      }
    }
  }

  static Object definition(String method, int id) throws Exception {
    return handlerClass.getMethod(method, int.class).invoke(handler, id);
  }

  static JSONArray rows(String name) throws Exception {
    JSONObject json = new JSONObject(new String(Files.readAllBytes(definitions.resolve(name)), "UTF-8"));
    return json.getJSONArray(json.keySet().iterator().next());
  }

  static void checkItems() throws Exception {
    Map<String, String> names = client
      ? mapping("isStackable", "stackable", "isWearable", "wieldable", "isMembersOnly", "membersItem",
          "isUntradable", "untradeable", "isNoteable", "noteable")
      : mapping("appearanceID", "appearanceId", "wearableID", "wearableId", "wearSlot", "wornItemIndex",
          "requiredSkillID", "requiredSkillIndex", "basePrice", "defaultPrice");
    Set<String> omitted = client ? skip("isFemaleOnly", "appearanceID", "wearSlot", "requiredLevel",
      "requiredSkillID", "armourBonus", "weaponAimBonus", "weaponPowerBonus", "magicBonus", "prayerBonus") : skip();
    int count = 0;
    for (String name : new String[]{"ItemDefs.json", "ItemDefsCustom.json"}) {
      for (Object raw : rows(name)) {
        JSONObject row = (JSONObject) raw;
        if (row.getInt("id") != count) throw new AssertionError("non-contiguous item ID");
        compare(definition("getItemDef", count), row, "item" + count, names, omitted); count++;
      }
    }
    if (count != 1593) throw new AssertionError("incomplete items");
    int actualCount = client ? ((Number) handlerClass.getMethod("itemCount").invoke(null)).intValue()
      : ((List<?>) field(handler, "items")).size();
    if (actualCount != count) throw new AssertionError("trailing/missing items");
    if (client) {
      JSONObject visuals = new JSONObject(new String(Files.readAllBytes(definitions.resolve("item-visuals.json")), "UTF-8"));
      for (Object raw : visuals.getJSONArray("items")) {
        JSONObject row = (JSONObject) raw;
        compare(definition("getItemDef", row.getInt("id")), row, "itemVisual" + row.getInt("id"),
          mapping("authenticSpriteId", "spriteID"), skip());
      }
    }
  }

  static void checkNpcs() throws Exception {
    Set<String> omitted = client ? skip("canEdit", "combatlvl", "isMembers", "aggressive", "ranged", "respawnTime", "roundMode")
      : skip("id", "canEdit");
    Map<String, String> names = mapping("command", "command1", "combatlvl", "combatLevel", "isMembers", "members");
    int count = 0;
    for (String name : new String[]{"NpcDefs.json", "NpcDefsCustom.json"}) {
      for (Object raw : rows(name)) {
        JSONObject row = (JSONObject) raw;
        if (row.getInt("id") != count) throw new AssertionError("non-contiguous NPC ID");
        // Reviewed historical customNpcConditions, independent of optional flags.
        if (count == 375 || count == 376) row.put("command", "pickpocket");
        compare(definition("getNpcDef", count), row, "npc" + count, names, omitted); count++;
      }
    }
    if (count != 836) throw new AssertionError("incomplete NPCs");
    int actualCount = client ? ((Number) handlerClass.getMethod("npcCount").invoke(null)).intValue()
      : ((List<?>) field(handler, "npcs")).size();
    if (actualCount != count) throw new AssertionError("trailing/missing NPCs");
  }

  static void checkDispatch() throws Exception {
    if (client) return;
    Class<?> constants = Class.forName("com.openrsc.server.constants.Constants");
    Class<?> spells = Class.forName("com.openrsc.server.constants.Spells");
    Map<?, ?> actual = (Map<?, ?>) constants.getMethod("currentSpellMap").invoke(null);
    JSONObject policy = new JSONObject(new String(Files.readAllBytes(definitions.resolve("effective-policy.json")), "UTF-8"));
    JSONArray dispatch = policy.getJSONArray("spellDispatch");
    if (actual.size() != dispatch.length() || dispatch.length() != 48) throw new AssertionError("public spell dispatch size");
    for (Object raw : dispatch) {
      JSONObject row = (JSONObject) raw; int id = row.getInt("id");
      Object selected = constants.getMethod("spellToEnum", int.class).invoke(null, id);
      if (!row.getString("spell").equals(String.valueOf(selected)) || !Integer.valueOf(id).equals(actual.get(selected)))
        throw new AssertionError("public spell dispatch changed at " + id);
      if (handlerClass.getMethod("getSpellDef", spells).invoke(handler, selected) != definition("getSpellDef", id))
        throw new AssertionError("reverse spell dispatch changed at " + id);
      comparisons += 3;
    }
    if (constants.getMethod("spellToEnum", int.class).invoke(null, -1) != null
        || constants.getMethod("spellToEnum", int.class).invoke(null, 48) != null)
      throw new AssertionError("unexpected public spell dispatch outside bounds");
  }

  static List<Element> children(Element parent) {
    List<Element> result = new ArrayList<>();
    for (Node node = parent.getFirstChild(); node != null; node = node.getNextSibling())
      if (node instanceof Element) result.add((Element) node);
    return result;
  }

  static void checkExtraNode(Element node, Object actual, String label) throws Exception {
    if (actual == null) throw new AssertionError("missing public extra " + label);
    List<Element> kids = children(node);
    if (actual instanceof Map) {
      Map<?, ?> map = (Map<?, ?>) actual; Set<Object> keys = new HashSet<>();
      for (Element entry : kids) {
        List<Element> pair = children(entry);
        if (!entry.getTagName().equals("entry") || pair.size() != 2) throw new AssertionError("malformed map fixture");
        Element key = pair.get(0); Object mapKey;
        if (key.getTagName().equals("int")) mapKey = Integer.valueOf(key.getTextContent().trim());
        else if (key.getTagName().equals("Point")) {
          mapKey = Class.forName("com.openrsc.server.model.Point").getMethod("location", int.class, int.class).invoke(null,
            Integer.parseInt(key.getElementsByTagName("x").item(0).getTextContent().trim()),
            Integer.parseInt(key.getElementsByTagName("y").item(0).getTextContent().trim()));
        } else throw new AssertionError("unreviewed extra map key " + key.getTagName());
        if (!keys.add(mapKey)) throw new AssertionError("duplicate public extra key");
        checkExtraNode(pair.get(1), map.get(mapKey), label + "[" + mapKey + "]");
      }
      if (map.size() != keys.size()) throw new AssertionError("trailing public extra map entries " + label);
    } else if (actual.getClass().isArray() || actual instanceof List) {
      int size = actual instanceof List ? ((List<?>) actual).size() : Array.getLength(actual);
      if (size != kids.size()) throw new AssertionError("public extra collection size " + label);
      for (int i = 0; i < size; i++) checkExtraNode(kids.get(i),
        actual instanceof List ? ((List<?>) actual).get(i) : Array.get(actual, i), label + "[" + i + "]");
    } else if (kids.isEmpty()) {
      String want = node.getTextContent(), got = String.valueOf(actual);
      boolean same = actual instanceof Number
        ? Double.compare(Double.parseDouble(want.trim()), ((Number) actual).doubleValue()) == 0 : got.equals(want);
      if (!same) throw new AssertionError("public extra field " + label + " expected=" + want + " actual=" + got);
      comparisons++;
    } else for (Element child : kids) checkExtraNode(child, field(actual, child.getTagName()), label + "." + child.getTagName());
  }

  static void checkExtras() throws Exception {
    if (client) return;
    Map<String, String> hooks = mapping("ItemHerbSecond", "herbSeconds", "ItemDartTipDef", "dartTips",
      "ItemGemDef", "gems", "ItemLogCutDef", "logCut", "ItemBowStringDef", "bowString", "ItemArrowHeadDef", "arrowHeads",
      "FiremakingDef", "firemaking", "ItemAffectedTypes", "itemAffectedTypes", "ItemUnIdentHerbDef", "itemUnIdentHerb",
      "ItemHerbDef", "itemHerb", "ItemEdibleHeals", "itemEdibleHeals", "ItemCookingDef", "itemCooking",
      "ItemPerfectCookingDef", "itemPerfectCooking", "ItemSmeltingDef", "itemSmelting", "ItemSmithingDef", "itemSmithing",
      "ItemCraftingDef", "itemCrafting", "ObjectMining", "objectMining", "ObjectWoodcutting", "objectWoodcutting",
      "ObjectFishing", "objectFishing", "ObjectTelePoints", "objectTelePoints", "NpcCerters", "certers");
    DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
    for (Map.Entry<String, String> hook : hooks.entrySet()) {
      Element root = factory.newDocumentBuilder().parse(definitions.resolve("extras/" + hook.getKey() + ".xml").toFile()).getDocumentElement();
      checkExtraNode(root, field(handler, hook.getValue()), hook.getKey());
    }
    if (!((Map<?, ?>) field(handler, "objectHarvesting")).isEmpty() || !((Map<?, ?>) field(handler, "objectRunecraft")).isEmpty())
      throw new AssertionError("Advanced skill hooks enabled");
  }

  static void checkSprites() throws Exception {
    if (!client) return;
    Class<?> surfaceClass = Class.forName("orsc.graphics.two.GraphicsController");
    Constructor<?> constructor = surfaceClass.getDeclaredConstructor(int.class, int.class, int.class);
    constructor.setAccessible(true); Object surface = constructor.newInstance(256, 256, 6000);
    if (!Boolean.TRUE.equals(surfaceClass.getMethod("fillSpriteTree").invoke(surface))) throw new AssertionError("stock sprite archive not loaded");
    Map<?, ?> tree = (Map<?, ?>) field(surface, "spriteTree");
    if (!new TreeSet<Object>(tree.keySet()).equals(new TreeSet<String>(Arrays.asList(
        "GUI", "GUIutil", "clipping", "crowns", "equipment", "items", "npc", "player", "projectiles", "skill_icons", "textures"))))
      throw new AssertionError("unexpected public stock sprite namespace");
    Method select = surfaceClass.getMethod("spriteSelect", Class.forName("com.openrsc.client.entityhandling.defs.ItemDef"));
    Method load = surfaceClass.getMethod("loadSprite", int.class, String.class);
    int selected = 0, nonblank = 0;
    for (int id = 0; id < 1593; id++) {
      Object item = definition("getItemDef", id);
      String[] location = String.valueOf(field(item, "spriteLocation")).split(":", -1);
      Map<?, ?> namespace = (Map<?, ?>) tree.get(location[0]);
      Object entry = namespace == null ? null : namespace.get(location[1]);
      Object expected;
      if (entry != null) {
        Object frames = entry.getClass().getMethod("getFrames").invoke(entry);
        if (Array.getLength(frames) < 1) throw new AssertionError("empty stock item frames " + id);
        Object frame = Array.get(frames, 0);
        expected = frame.getClass().getMethod("getSprite").invoke(frame);
      } else {
        int sprite = ((Number) field(item, "spriteID")).intValue();
        if (sprite < 0) throw new AssertionError("stock item has no authoritative sprite " + id + " " + Arrays.toString(location));
        java.util.zip.ZipFile archive = (java.util.zip.ZipFile) field(surface, "spriteArchive");
        if (archive.getEntry(String.valueOf(2150 + sprite)) == null) throw new AssertionError("stock sprite fallback absent " + id);
        load.invoke(surface, 2150 + sprite, "public-stock");
        expected = Array.get(field(surface, "sprites"), 2150 + sprite);
      }
      Object actual = select.invoke(surface, item);
      int[] expectedPixels = (int[]) expected.getClass().getMethod("getPixels").invoke(expected);
      int[] actualPixels = (int[]) actual.getClass().getMethod("getPixels").invoke(actual);
      if (!Arrays.equals(expectedPixels, actualPixels)) throw new AssertionError("wrong selected stock sprite pixels " + id);
      if (expectedPixels.length < 1) throw new AssertionError("zero size stock sprite " + id);
      for (int pixel : expectedPixels) if (pixel != 0) { nonblank++; break; }
      selected++;
    }
    java.util.zip.ZipFile archive = (java.util.zip.ZipFile) field(surface, "spriteArchive");
    if (archive != null) archive.close();
    // An authored project sprite remains the primary selection after stock load.
    Object project = select.invoke(surface, definition("getItemDef", 1));
    ((Map) field(surface, "projectItemSprites")).put(Integer.valueOf(0), project);
    if (select.invoke(surface, definition("getItemDef", 0)) != project)
      throw new AssertionError("stock visual selection overwrote authored project sprite");
    System.out.println("PUBLIC_STOCK_ITEM_PIXELS_VERIFIED selected=" + selected + " nonblank=" + nonblank);
  }

  static void checkXml(String file, String method, Map<String, String> names) throws Exception {
    DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
    NodeList rows = factory.newDocumentBuilder().parse(definitions.resolve(file).toFile())
      .getDocumentElement().getChildNodes();
    int id = 0;
    for (int i = 0; i < rows.getLength(); i++) {
      if (!(rows.item(i) instanceof Element)) continue;
      Element row = (Element) rows.item(i); JSONObject fields = new JSONObject();
      NodeList children = row.getChildNodes();
      for (int j = 0; j < children.getLength(); j++) {
        if (children.item(j) instanceof Element) {
          Element child = (Element) children.item(j);
          if (!"requiredRunes".equals(child.getTagName())) {
            String value = child.getTextContent();
            String key = child.getTagName();
            if (!Arrays.asList("name", "description", "command1", "command2", "objectModel").contains(key)) value = value.trim();
            fields.put(key, value);
          }
        }
      }
      compare(definition(method, id), fields, file + id, names,
        client && file.equals("SpellDef.xml") ? skip("members", "evil", "exp") : skip());
      if (file.equals("SpellDef.xml")) {
        Map<Integer, Integer> expectedRunes = new HashMap<>();
        NodeList entries = row.getElementsByTagName("entry");
        for (int j = 0; j < entries.getLength(); j++) {
          NodeList pair = ((Element) entries.item(j)).getElementsByTagName("int");
          if (pair.getLength() != 2 || expectedRunes.put(Integer.parseInt(pair.item(0).getTextContent().trim()),
              Integer.parseInt(pair.item(1).getTextContent().trim())) != null) throw new AssertionError("duplicate/invalid expected rune map");
        }
        if (!expectedRunes.equals(field(definition(method, id), "requiredRunes")))
          throw new AssertionError("spell rune ID/count mismatch " + id);
        comparisons += expectedRunes.size();
      }
      id++;
    }
    String[] files = {"GameObjectDef.xml", "DoorDef.xml", "TileDef.xml", "PrayerDef.xml", "SpellDef.xml"};
    String[] countMethods = {"objectCount", "doorCount", "tileCount", "prayerCount", "spellCount"};
    String[] fields = {"gameObjects", "doors", "tiles", "prayers", "spells"};
    int index = Arrays.asList(files).indexOf(file);
    int actualCount = client ? ((Number) handlerClass.getMethod(countMethods[index]).invoke(null)).intValue()
      : Array.getLength(field(handler, fields[index]));
    if (id != actualCount) throw new AssertionError("unexpected trailing/missing " + file + " definitions");
  }

  public static void main(String[] args) throws Exception {
    try { run(args); } catch (Throwable failure) { failure.printStackTrace(); System.exit(1); }
  }

  static void run(String[] args) throws Exception {
    client = "client".equals(args[0]); definitions = Paths.get(args[1]);
    if (client) {
      Class.forName("orsc.CurrentCompositionIdentity").getMethod("initializeFromSystemProperties").invoke(null);
      Class.forName("orsc.Config").getField("F_CACHE_DIR").set(null, Paths.get("Cache").toAbsolutePath().toString());
      handlerClass = Class.forName("com.openrsc.client.entityhandling.EntityHandler");
      handlerClass.getMethod("load", boolean.class).invoke(null, true);
    } else {
      Class.forName("com.openrsc.server.CurrentCompositionIdentity").getMethod("initializeFromSystemProperties").invoke(null);
      server = Class.forName("com.openrsc.server.Server").getConstructor(String.class).newInstance("current-base.conf");
      handler = server.getClass().getMethod("getEntityHandler").invoke(server);
      handlerClass = handler.getClass(); handlerClass.getMethod("load").invoke(handler);
    }
    checkItems(); checkNpcs();
    checkXml("GameObjectDef.xml", client ? "getObjectDef" : "getGameObjectDef", mapping());
    checkXml("DoorDef.xml", "getDoorDef", client ? mapping("modelVar1", "wallObjectHeight") : mapping());
    checkXml("TileDef.xml", "getTileDef", client ? mapping("unknown", "tileValue") : mapping());
    checkXml("PrayerDef.xml", "getPrayerDef", mapping());
    checkXml("SpellDef.xml", "getSpellDef", mapping());
    checkDispatch();
    checkExtras();
    checkSprites();
    if (!errors.isEmpty()) throw new AssertionError(String.join("\n", errors));
    System.out.println("PUBLIC_DEFINITIONS_VERIFIED role=" + args[0] + " comparisons=" + comparisons);
    System.exit(0);
  }
}

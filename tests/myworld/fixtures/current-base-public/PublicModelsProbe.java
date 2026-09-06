import java.lang.reflect.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import org.json.*;
import org.w3c.dom.*;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.data.DataOperations;
import orsc.graphics.three.RSModel;

/** Actual archive lookup, OB3 decode and mudclient loadModels; no game/network startup. */
public final class PublicModelsProbe {
  static Object field(Object instance, String name) throws Exception {
    Field field = instance.getClass().getDeclaredField(name); field.setAccessible(true); return field.get(instance);
  }
  static int count(Object model, String name) throws Exception { return ((Number) field(model, name)).intValue(); }
  static String sha(byte[] bytes) throws Exception {
    StringBuilder out = new StringBuilder();
    for (byte value : MessageDigest.getInstance("SHA-256").digest(bytes)) out.append(String.format("%02x", value & 255));
    return out.toString();
  }
  public static void main(String[] args) throws Exception {
    orsc.CurrentCompositionIdentity.initializeFromSystemProperties();
    orsc.Config.F_CACHE_DIR = Paths.get("Cache").toAbsolutePath().toString();
    EntityHandler.load(true);
    byte[] packed = Files.readAllBytes(Paths.get("Cache/video/models.orsc"));
    if (!sha(packed).equals("fcde7214b1730d50d840767a9af0448d683b544ef94fa011380e358c3680d23f")) throw new AssertionError("model archive identity");
    byte[] models = Arrays.copyOfRange(packed, 6, packed.length);
    JSONArray visuals = new JSONObject(new String(Files.readAllBytes(Paths.get(args[1], "scenery-visuals.json")), "UTF-8")).getJSONArray("scenery");
    int resolved = 0, empty = 0;
    for (int id = 0; id < 1296; id++) {
      String name = EntityHandler.getObjectDef(id).getObjectModel();
      if (!name.equals(visuals.getJSONObject(id).getString("objectModel"))) throw new AssertionError("model selection " + id);
      int offset = DataOperations.getDataFileOffset(name + ".ob3", models);
      if (offset == 0) throw new AssertionError("missing stock model " + id + " " + name);
      RSModel model = new RSModel(models, offset, true);
      if (count(model, "vertHead") == 0 || count(model, "faceHead") == 0) {
        if (id != 211 || !name.equals("runiteruck1") || count(model, "vertHead") != 0 || count(model, "faceHead") != 0)
          throw new AssertionError("unexpected empty stock model " + id);
        RSModel historical = new RSModel(1, 1);
        if (count(historical, "vertHead") != count(model, "vertHead") || count(historical, "faceHead") != count(model, "faceHead"))
          throw new AssertionError("placeholder differs from historical active geometry");
        empty++;
      } else resolved++;
    }
    if (resolved != 1295 || empty != 1) throw new AssertionError("stock model coverage");
    // Invoke the production startup loop with a test-only no-UI port. Allocation avoids unrelated startup.
    Class<?> port = Class.forName("orsc.multiclient.ClientPort");
    Object noUiPort = Proxy.newProxyInstance(port.getClassLoader(), new Class<?>[]{port}, (proxy, method, values) -> {
      if (method.getName().equals("getCacheLocation")) return orsc.Config.F_CACHE_DIR + java.io.File.separator;
      if (method.getReturnType() == boolean.class) return false;
      if (method.getReturnType() == int.class) return 0;
      return null;
    });
    Class<?> client = Class.forName("orsc.mudclient");
    client.getField("clientPort").set(null, noUiPort);
    Class<?> unsafeClass = Class.forName("sun.misc.Unsafe");
    Field singleton = unsafeClass.getDeclaredField("theUnsafe"); singleton.setAccessible(true);
    Object instance = unsafeClass.getMethod("allocateInstance", Class.class).invoke(singleton.get(null), client);
    Field cache = client.getDeclaredField("modelCache"); cache.setAccessible(true); cache.set(instance, new RSModel[1000]);
    Method load = client.getDeclaredMethod("loadModels"); load.setAccessible(true); load.invoke(instance);
    RSModel[] loaded = (RSModel[]) cache.get(instance);
    if (count(loaded[EntityHandler.getObjectDef(211).modelID], "vertHead") != 0) throw new AssertionError("startup placeholder not empty");
    // A later authored definition is primary, including this stock ID. No stock geometry is forced on it.
    DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
    Document document = factory.newDocumentBuilder().parse(Paths.get(args[1], "GameObjectDef.xml").toFile());
    Element authored = (Element) document.getDocumentElement().getElementsByTagName("GameObjectDef").item(211);
    authored.getElementsByTagName("objectModel").item(0).setTextContent("tree2");
    Path override = Paths.get("authored-scenery.xml");
    TransformerFactory.newInstance().newTransformer().transform(new DOMSource(document), new StreamResult(override.toFile()));
    Method project = EntityHandler.class.getDeclaredMethod("loadProjectScenery", Path.class); project.setAccessible(true);
    project.invoke(null, override); load.invoke(instance);
    if (!EntityHandler.getObjectDef(211).getObjectModel().equals("tree2")
        || count(loaded[EntityHandler.getObjectDef(211).modelID], "vertHead") < 1) throw new AssertionError("authored model did not win");
    Element unknown = (Element) authored.cloneNode(true);
    unknown.getElementsByTagName("objectModel").item(0).setTextContent("unreviewed_missing_public_model");
    document.getDocumentElement().appendChild(unknown);
    TransformerFactory.newInstance().newTransformer().transform(new DOMSource(document), new StreamResult(override.toFile()));
    project.invoke(null, override);
    try { load.invoke(instance); throw new AssertionError("unknown authored model accepted"); }
    catch (InvocationTargetException expected) {
      if (!(expected.getCause() instanceof IllegalStateException)
          || !expected.getCause().getMessage().contains("missing model unreviewed_missing_public_model")) throw expected;
    }
    System.out.println("PUBLIC_MODELS_VERIFIED resolved=1295 explicitEmpty=1 actualStartup=true authoredOverride=true missingRefused=true");
  }
}

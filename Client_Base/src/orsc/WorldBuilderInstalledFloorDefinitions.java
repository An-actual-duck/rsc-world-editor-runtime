package orsc;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import org.json.JSONObject;

/** Exact, transaction-installed floor catalog for the normal player client. */
public final class WorldBuilderInstalledFloorDefinitions {
    public static final String DESCRIPTOR = "world-builder-configs/installed-floors.json";
    public static final String DEFINITIONS = "world-builder-configs/TileDef.xml";

    public static byte[] loadConfigured() throws IOException {
        return load(Paths.get(".").toAbsolutePath().normalize());
    }

    /** Adds verified map materials while retaining every existing target definition object. */
    public static void appendTo(java.util.List<com.openrsc.client.entityhandling.defs.TileDef> existing)
            throws IOException {
        byte[] bytes = loadConfigured();
        if (bytes == null) return;
        try {
            javax.xml.parsers.DocumentBuilderFactory factory = javax.xml.parsers.DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(javax.xml.XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(javax.xml.XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);
            org.w3c.dom.Element root = factory.newDocumentBuilder()
                .parse(new java.io.ByteArrayInputStream(bytes)).getDocumentElement();
            if (!"TileDef-array".equals(root.getTagName()) || root.hasAttributes())
                throw new IOException("Invalid installed floor root");
            java.util.List<com.openrsc.client.entityhandling.defs.TileDef> supplied = new java.util.ArrayList<>();
            for (org.w3c.dom.Node node = root.getFirstChild(); node != null; node = node.getNextSibling()) {
                if (!(node instanceof org.w3c.dom.Element)) continue;
                org.w3c.dom.Element row = (org.w3c.dom.Element) node;
                if (!"TileDef".equals(row.getTagName()) || row.hasAttributes() || supplied.size() >= 249)
                    throw new IOException("Invalid installed floor inventory");
                java.util.Map<String, String> fields = new java.util.HashMap<>();
                for (org.w3c.dom.Node child = row.getFirstChild(); child != null; child = child.getNextSibling()) {
                    if (!(child instanceof org.w3c.dom.Element)) continue;
                    String key = child.getNodeName();
                    org.w3c.dom.Element field = (org.w3c.dom.Element) child;
                    if (field.hasAttributes() || field.getElementsByTagName("*").getLength() != 0
                            || !Arrays.asList("colour", "unknown", "objectType", "worldBuilderMaterial",
                            "worldBuilderSourceOverlay").contains(key) || fields.put(key, child.getTextContent().trim()) != null)
                        throw new IOException("Invalid installed floor field");
                }
                if (fields.containsKey("worldBuilderMaterial") && fields.get("worldBuilderMaterial").isEmpty()
                        || fields.containsKey("worldBuilderSourceOverlay")
                            && Integer.parseInt(fields.get("worldBuilderSourceOverlay")) <= 0)
                    throw new IOException("Invalid installed floor metadata");
                supplied.add(new com.openrsc.client.entityhandling.defs.TileDef(
                    Integer.parseInt(fields.get("colour")), Integer.parseInt(fields.get("unknown")),
                    Integer.parseInt(fields.get("objectType")), fields.getOrDefault("worldBuilderMaterial", ""),
                    Integer.parseInt(fields.getOrDefault("worldBuilderSourceOverlay", "0"))));
            }
            com.openrsc.client.entityhandling.defs.TileDef.validateWorldBuilderDefinitions(supplied);
            if (supplied.size() < existing.size()) throw new IOException("Installed floors remove target definitions");
            for (int index = 0; index < existing.size(); index++) {
                com.openrsc.client.entityhandling.defs.TileDef before = existing.get(index), after = supplied.get(index);
                if (before == null || before.getColour() != after.getColour()
                        || before.getTileValue() != after.getTileValue() || before.getObjectType() != after.getObjectType()
                        || !before.getWorldBuilderMaterial().equals(after.getWorldBuilderMaterial())
                        || before.getWorldBuilderSourceOverlay() != after.getWorldBuilderSourceOverlay())
                    throw new IOException("Installed floors conflict with target definition " + (index + 1));
            }
            existing.addAll(supplied.subList(existing.size(), supplied.size()));
        } catch (IOException failure) {
            throw failure;
        } catch (Exception failure) {
            throw new IOException("Invalid installed floor definitions", failure);
        }
    }

    public static byte[] load(Path clientRoot) throws IOException {
        Path root = clientRoot.toAbsolutePath().normalize();
        Path descriptor = root.resolve(DESCRIPTOR);
        if (!Files.exists(descriptor, LinkOption.NOFOLLOW_LINKS)) {
            if (Files.exists(root.resolve(DEFINITIONS), LinkOption.NOFOLLOW_LINKS))
                throw new IOException("Installed floor XML requires its verified descriptor");
            return null;
        }
        try {
            requireFile(root, descriptor, 16384);
            JSONObject value = new JSONObject(new String(Files.readAllBytes(descriptor), StandardCharsets.UTF_8));
            if (!value.keySet().equals(new HashSet<String>(Arrays.asList("schemaVersion", "manifestType",
                    "tileDefinitionsRelativePath", "tileDefinitionsSha256")))
                || !(value.get("schemaVersion") instanceof Integer) || value.getInt("schemaVersion") != 1
                || !"world-builder-installed-floor-definitions".equals(value.get("manifestType"))
                || !DEFINITIONS.equals(value.get("tileDefinitionsRelativePath")))
                throw new IOException("Unsupported installed floor descriptor");
            Object expected = value.get("tileDefinitionsSha256");
            if (!(expected instanceof String) || !((String) expected).matches("[0-9a-f]{64}"))
                throw new IOException("Invalid installed floor SHA-256");
            Path definitions = root.resolve(DEFINITIONS);
            requireFile(root, definitions, 2 * 1024 * 1024);
            byte[] bytes = Files.readAllBytes(definitions);
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder actual = new StringBuilder();
            for (byte part : digest) actual.append(String.format(java.util.Locale.ROOT, "%02x", part & 255));
            if (!expected.equals(actual.toString())) throw new IOException("Installed floor SHA-256 mismatch");
            return bytes;
        } catch (IOException failure) {
            throw failure;
        } catch (Exception failure) {
            throw new IOException("Invalid installed floor definitions", failure);
        }
    }

    private static void requireFile(Path root, Path path, long maximum) throws IOException {
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path)
                || Files.isSymbolicLink(path.getParent()) || !path.toRealPath().equals(root.toRealPath().resolve(root.relativize(path)))
                || Files.size(path) > maximum)
            throw new IOException("Missing or unsafe installed floor file: " + path.getFileName());
    }

    private WorldBuilderInstalledFloorDefinitions() { }
}

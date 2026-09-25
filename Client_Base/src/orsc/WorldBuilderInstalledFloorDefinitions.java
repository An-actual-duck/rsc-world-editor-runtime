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

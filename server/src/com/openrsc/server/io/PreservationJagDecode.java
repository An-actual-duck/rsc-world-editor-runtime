package com.openrsc.server.io;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.DirectoryStream;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

/** Inventory-bound, decode-only bridge for the reviewed default Preservation server archives. */
public final class PreservationJagDecode {
    private static final String CONTRACT_SHA256 = "1dd693a742c5a0a92669feac187015acdd15586073b8d62d544dde1b5dd24f1a";
    private static final String DECODER = "preservation-r64-jag-decode-v1";
    private static final String[] ROLES = {"maps-free", "maps-members", "land-free", "land-members"};
    private static final int[] SIZES = {37613, 60002, 142219, 155110};
    private static final String[] HASHES = {
        "7e85a47c95ba690187ad10d8218f9b4e327b54c27e6f3da18229b061de35a2d1",
        "6a43ffc81a5d95fe392a27fed347eea1c27ac87d11c5670b9e3f0dfe4a8fc7f7",
        "6f0720a29d40f5dfcd477049d014b41422742d2e3a9900144287f835cc99813b",
        "c38cfcb1e8dddb17afd3ec9d0e8f0cdb076df2caf40a648bf6dd8ea400a55df0"
    };

    private PreservationJagDecode() { }

    public static void main(String[] arguments) {
        try {
            execute(arguments);
            System.out.println("Reviewed Preservation JAG sectors decoded; runtime promotion remains unapproved");
        } catch (Exception failure) {
            // Never disclose supplied paths; preserve any new partial output for explicit recovery.
            System.err.println("Preservation JAG decode refused: " + failure.getClass().getSimpleName()
                + "; no success evidence is authoritative without exit zero; retain partial output for recovery");
            System.exit(2);
        }
    }

    private static void execute(String[] arguments) throws Exception {
        Map<String, String> options = options(arguments);
        Path contract = input(options.get("contract"));
        byte[] contractBytes = read(contract, 1048576);
        if (!CONTRACT_SHA256.equals(hash(contractBytes)))
            throw new IOException("unreviewed decoder contract");
        JSONObject specification = new JSONObject(new String(contractBytes, StandardCharsets.UTF_8))
            .getJSONObject("legacyMapDecoding");
        Path output = output(options.get("output"));
        Path evidencePath = output(options.get("evidence"));
        disjoint(output, evidencePath); disjoint(output, contract); disjoint(evidencePath, contract);
        Path[] inputs = new Path[4];
        BoundedJagArchive[] archives = new BoundedJagArchive[4];
        JSONArray sourceInventory = new JSONArray();
        for (int index = 0; index < ROLES.length; index++) {
            Path path = input(options.get(ROLES[index])); inputs[index] = path;
            disjoint(output, path); disjoint(evidencePath, path);
            if (Files.isSameFile(path, contract)) throw new IOException("input roles alias");
            for (int earlier = 0; earlier < index; earlier++)
                if (Files.isSameFile(path, inputs[earlier])) throw new IOException("input roles alias");
            byte[] bytes = read(path, BoundedJagArchive.MAX_ARCHIVE_BYTES);
            if (bytes.length != SIZES[index] || !HASHES[index].equals(hash(bytes)))
                throw new IOException("archive does not match the reviewed role inventory");
            BoundedJagArchive archive = new BoundedJagArchive(bytes); archives[index] = archive;
            sourceInventory.put(new JSONObject().put("role", ROLES[index]).put("size", bytes.length)
                .put("sha256", HASHES[index]).put("entryCount", archive.entryCount())
                .put("expandedBytes", archive.expandedBytes()));
        }

        List<byte[]> sectors = new ArrayList<byte[]>();
        List<String> names = new ArrayList<String>();
        JSONArray inventory = new JSONArray();
        int absent = 0, directions = 0, overlays = 0, signed = 0;
        for (int plane = 0; plane < 4; plane++) for (int x = 48; x <= 68; x++)
            for (int y = 37; y <= 56; y++) {
                String mapName = "m" + plane + x + y;
                HistoricalJagSectorDecoder.Result decoded = HistoricalJagSectorDecoder.decode(
                    archives[0], archives[1], archives[2], archives[3], x, y, plane, true, false, true);
                JSONObject row = new JSONObject().put("plane", plane).put("archiveX", x)
                    .put("archiveY", y).put("present", decoded.sector() != null)
                    .put("sources", new JSONObject()
                        .put("jm", selected(archives, mapName + ".jm", 0, 1))
                        .put("dat", selected(archives, mapName + ".dat", 0, 1))
                        .put("hei", selected(archives, mapName + ".hei", 2, 3))
                        .put("loc", archives[0].contains(mapName + ".loc") ? ROLES[0] : "absent"));
                if (decoded.sector() == null) { absent++; inventory.put(row); continue; }
                byte[] raw = decoded.sector().pack().array();
                if (raw.length != 23040) throw new IOException("unexpected raw sector length");
                String name = "h" + plane + "x" + x + "y" + y + ".raw";
                int directionCount = 0, overlayCount = 0, signedCount = 0;
                byte[] discarded = decoded.discardedTileDirections();
                for (int tile = 0; tile < 2304; tile++) {
                    if (discarded[tile] != 0) directionCount++;
                    if (decoded.sector().getTile(tile).getGroundOverlay() == 250) overlayCount++;
                    if (decoded.sector().getTile(tile).getDiagonalWalls() < 0) signedCount++;
                }
                directions += directionCount; overlays += overlayCount; signed += signedCount;
                row.put("relativePath", name).put("size", raw.length).put("sha256", hash(raw))
                    .put("discardedTileDirectionSha256", hash(discarded))
                    .put("discardedNonzeroDirectionTiles", directionCount)
                    .put("overlay250Tiles", overlayCount).put("signedNegativeDiagonalTiles", signedCount);
                inventory.put(row); sectors.add(raw); names.add(name);
            }
        requireUnchanged(inputs, contract);
        Files.createDirectory(output);
        for (int index = 0; index < sectors.size(); index++) {
            Path file = output.resolve(names.get(index)); byte[] bytes = sectors.get(index);
            Files.write(file, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            if (!hash(bytes).equals(hash(read(file, 23040))))
                throw new IOException("written sector verification failed");
        }
        requireUnchanged(inputs, contract);
        verifyOutput(output, names, sectors);
        JSONObject evidence = new JSONObject()
            .put("schemaId", "preservation-jag-decode-evidence-v1")
            .put("manifestType", "preservation-jag-decode-evidence")
            .put("decoderId", DECODER).put("status", "decoded")
            .put("contractSha256", CONTRACT_SHA256)
            .put("source", new JSONObject().put("archives", sourceInventory).put("unchanged", true))
            .put("policy", specification.getJSONObject("decodingPolicy"))
            .put("summary", new JSONObject().put("probeCount", inventory.length())
                .put("presentSectorCount", sectors.size()).put("absentSectorCount", absent)
                .put("discardedNonzeroDirectionTiles", directions).put("overlay250Tiles", overlays)
                .put("signedNegativeDiagonalTiles", signed))
            .put("inventory", inventory)
            .put("inventorySha256", hash(canonical(inventory).getBytes(StandardCharsets.UTF_8)));
        byte[] evidenceBytes = (canonical(evidence) + "\n").getBytes(StandardCharsets.UTF_8);
        if (evidenceBytes.length > 2097152) throw new IOException("evidence exceeds reviewed limit");
        Files.write(evidencePath, evidenceBytes,
            StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
    }

    private static void verifyOutput(Path root, List<String> names, List<byte[]> sectors)
        throws Exception {
        if (!root.equals(root.toRealPath())) throw new IOException("output directory was aliased");
        TreeSet<String> actual = new TreeSet<String>();
        try (DirectoryStream<Path> files = Files.newDirectoryStream(root)) {
            for (Path file : files) {
                if (!actual.add(file.getFileName().toString()) || actual.size() > names.size())
                    throw new IOException("output inventory changed");
            }
        }
        if (!actual.equals(new TreeSet<String>(names))) throw new IOException("output inventory changed");
        for (int index = 0; index < names.size(); index++)
            if (!hash(sectors.get(index)).equals(hash(read(input(root.resolve(names.get(index)).toString()), 23040))))
                throw new IOException("output sector changed");
    }

    private static String selected(BoundedJagArchive[] archives, String name, int free, int member) {
        return archives[member].contains(name) ? ROLES[member]
            : archives[free].contains(name) ? ROLES[free] : "absent";
    }

    private static Map<String, String> options(String[] arguments) throws IOException {
        if (arguments.length != 14) throw new IOException("wrong closed argument count");
        Map<String, String> values = new LinkedHashMap<String, String>();
        for (int index = 0; index < arguments.length; index += 2) {
            String key = arguments[index];
            if (!key.startsWith("--") || values.put(key.substring(2), arguments[index + 1]) != null)
                throw new IOException("repeated or invalid argument");
        }
        if (!values.keySet().equals(new TreeSet<String>(Arrays.asList("contract", "maps-free",
            "maps-members", "land-free", "land-members", "output", "evidence"))))
            throw new IOException("unreviewed argument");
        return values;
    }

    private static Path input(String value) throws IOException {
        Path path = Paths.get(value);
        if (!path.isAbsolute() || !path.equals(path.normalize()) || !path.equals(path.toRealPath())
            || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("input is not a canonical regular file");
        try {
            if (((Number) Files.getAttribute(path, "unix:nlink", LinkOption.NOFOLLOW_LINKS)).longValue() != 1)
                throw new IOException("input has hard-link aliases");
        } catch (UnsupportedOperationException unsupported) {
            throw new IOException("input alias checks require POSIX support", unsupported);
        }
        return path;
    }

    private static Path output(String value) throws IOException {
        Path path = Paths.get(value);
        if (!path.isAbsolute() || !path.equals(path.normalize()) || path.getParent() == null
            || !path.getParent().equals(path.getParent().toRealPath())
            || !Files.isDirectory(path.getParent(), LinkOption.NOFOLLOW_LINKS)
            || Files.exists(path, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("output must be new with a canonical existing parent");
        return path;
    }

    private static void disjoint(Path left, Path right) throws IOException {
        if (left.startsWith(right) || right.startsWith(left))
            throw new IOException("inputs and outputs overlap");
    }

    private static byte[] read(Path path, int maximum) throws IOException {
        try (InputStream input = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int count;
            while ((count = input.read(buffer)) >= 0) {
                if ((long) output.size() + count > maximum) throw new IOException("input exceeds limit");
                output.write(buffer, 0, count);
            }
            return output.toByteArray();
        }
    }

    private static void requireUnchanged(Path[] inputs, Path contract) throws Exception {
        for (int index = 0; index < inputs.length; index++)
            if (!HASHES[index].equals(hash(read(input(inputs[index].toString()),
                BoundedJagArchive.MAX_ARCHIVE_BYTES)))) throw new IOException("source archive changed");
        if (!CONTRACT_SHA256.equals(hash(read(input(contract.toString()), 1048576))))
            throw new IOException("decoder contract changed");
    }

    private static String hash(byte[] bytes) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(bytes))
            result.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }

    private static String canonical(Object value) {
        if (value instanceof JSONObject) {
            JSONObject object = (JSONObject) value; StringBuilder result = new StringBuilder("{");
            for (String key : new TreeSet<String>(object.keySet())) {
                if (result.length() > 1) result.append(',');
                result.append(JSONObject.quote(key)).append(':').append(canonical(object.get(key)));
            }
            return result.append('}').toString();
        }
        if (value instanceof JSONArray) {
            JSONArray array = (JSONArray) value; StringBuilder result = new StringBuilder("[");
            for (int index = 0; index < array.length(); index++) {
                if (index > 0) result.append(','); result.append(canonical(array.get(index)));
            }
            return result.append(']').toString();
        }
        return value instanceof String ? JSONObject.quote((String) value) : value.toString();
    }
}

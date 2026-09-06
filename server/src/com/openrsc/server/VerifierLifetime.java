package com.openrsc.server;

import org.json.*;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.*;
import java.util.*;

/** POSIX invocation revocation and actual-JVM leases. No game/logging dependency. */
public final class VerifierLifetime {
    public static final List<String> INPUTS = Arrays.asList("client-profile", "composition-identity", "contract",
        "installed-client-root", "installed-server-root", "map-package", "runtime-profile", "server-config",
        "server-profile", "state-db");
    private static final List<FileChannel> CHANNELS = new ArrayList<>();
    private static final List<FileLock> LOCKS = new ArrayList<>();
    private final JSONObject authority;
    private final Path authorityPath, control, workspace;
    private final String authorityHash;
    private boolean supervisorOwned, closed;
    private String intentHash;
    private String childIntentHash;

    public static final class Busy extends IOException {
        public Busy() { super("Verifier invocation still has an owned process lease"); }
    }

    private VerifierLifetime(Path path, String expected) throws Exception {
        authorityPath = privateFile(path);
        authorityHash = hash(read(authorityPath));
        require(hashValue(expected).equals(authorityHash), "Supervision authority hash differs");
        authority = object(read(authorityPath));
        keys(authority, "schemaVersion", "manifestType", "invocationId", "controlRoot", "workspace",
            "invocationSha256", "compositionIdentitySha256", "verifierContractSha256", "inputPaths", "files");
        identity(authority, "current-base-verifier-supervision");
        require(UUID.fromString(authority.getString("invocationId")).toString().equals(authority.getString("invocationId")),
            "Invocation UUID is not canonical");
        hashValue(authority.getString("invocationSha256"));
        hashValue(authority.getString("compositionIdentitySha256"));
        hashValue(authority.getString("verifierContractSha256"));
        control = directory(path(authority.getString("controlRoot")));
        require(Files.getPosixFilePermissions(control).equals(PosixFilePermissions.fromString("rwx------")),
            "Supervision control root must be 0700");
        require(authorityPath.equals(control.resolve("authority.json")), "Authority has wrong fixed path");
        workspace = path(authority.getString("workspace"));
        disjoint(control, workspace);
        JSONObject inputs = authority.getJSONObject("inputPaths");
        keys(inputs, INPUTS.toArray(new String[0]));
        for (String name : INPUTS) {
            Path input = path(inputs.getString(name));
            disjoint(control, input); disjoint(workspace, input);
        }
        keys(authority.getJSONObject("files"), "supervisor", "server", "client", "intent");
        for (String role : Arrays.asList("supervisor", "server", "client", "intent")) checkAnchor(role);
    }

    public static VerifierLifetime supervisor(Map<String,String> options) throws Exception {
        VerifierLifetime owner = new VerifierLifetime(path(options.get("supervision")), options.get("supervision-sha256"));
        require(owner.authority.getString("invocationSha256").equals(invocationHash(options)), "Invocation arguments differ");
        require(owner.workspace.equals(path(options.get("workspace"))), "Invocation workspace differs");
        require(owner.authority.getString("compositionIdentitySha256").equals(hash(read(path(options.get("composition-identity"))))),
            "Composition identity differs from supervision authority");
        require(owner.authority.getString("verifierContractSha256").equals(hash(read(path(options.get("contract"))))),
            "Verifier contract differs from supervision authority");
        for (String name : INPUTS)
            require(owner.authority.getJSONObject("inputPaths").getString(name).equals(options.get(name)),
                "Supervision input inventory differs from invocation");
        owner.validateOutput(path(options.get("evidence")));
        owner.acquire("supervisor"); owner.supervisorOwned = true;
        owner.requireOpen();
        require(Files.size(owner.checkAnchor("intent")) == 0, "Verifier invocation cannot be restarted");
        return owner;
    }

    public static VerifierLifetime child(String[] arguments, String role) throws Exception {
        Map<String,String> options = options(arguments, "supervision", "supervision-sha256", "intent-sha256");
        VerifierLifetime owner = new VerifierLifetime(path(options.get("supervision")), options.get("supervision-sha256"));
        require(role.equals("server") || role.equals("client"), "Unsupported verifier child role");
        owner.acquire(role);
        owner.requireOpen();
        JSONObject intent = owner.intent();
        require(intent != null && hashValue(options.get("intent-sha256")).equals(owner.intentHash), "Sealed child intent differs");
        owner.childIntentHash = options.get("intent-sha256");
        require(Paths.get("").toRealPath().equals(owner.workspace.resolve("execution/" + role)), "Verifier child working root differs");
        owner.requireOpen();
        return owner;
    }

    public static VerifierLifetime recovery(Path authority, String hash, Path contract) throws Exception {
        VerifierLifetime owner = new VerifierLifetime(authority, hash);
        require(owner.authority.getString("verifierContractSha256").equals(hash(read(contract))), "Recovery contract binding differs");
        owner.acquire("supervisor"); owner.supervisorOwned = true;
        return owner;
    }

    /** Runtime-created nonce and exact credential ownership are sealed before any child is spawned. */
    public synchronized void credential(byte[] bytes) throws Exception {
        require(supervisorOwned, "Only supervisor may create credential intent");
        requireOpen();
        Path slot = workspace.resolve("execution/credential.json");
        require(bytes.length > 0 && bytes.length <= 65536, "Credential exceeds bound");
        require(Files.size(checkAnchor("intent")) == 0, "Intent already populated");
        Files.createFile(slot, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
        syncDirectory(slot.getParent());
        JSONObject credential = fileIdentity(privateFile(slot));
        credential.put("relativePath", "execution/credential.json");
        credential.put("sha256", hash(bytes)); credential.put("size", bytes.length);
        JSONObject intent = record("current-base-verifier-intent");
        intent.put("state", "open");
        byte[] nonce = new byte[32]; new SecureRandom().nextBytes(nonce);
        intent.put("nonce", hex(nonce)); intent.put("credential", credential);
        byte[] encoded = encode(intent);
        writeEmpty(checkAnchor("intent"), encoded);
        syncDirectory(control);
        intentHash = hash(encoded);
        requireOpen();
        writeEmpty(slot, bytes);
        syncDirectory(slot.getParent());
    }

    public synchronized List<String> childArguments() throws Exception {
        requireOpen(); require(intent() != null, "Child requires sealed intent");
        return Arrays.asList("--supervision", authorityPath.toString(), "--supervision-sha256", authorityHash,
            "--intent-sha256", intentHash);
    }

    public synchronized void requireOpen() throws Exception {
        require(!closed && !Files.exists(control.resolve("revocation.json"), LinkOption.NOFOLLOW_LINKS),
            "Verifier invocation was permanently revoked");
        require(hash(read(privateFile(authorityPath))).equals(authorityHash), "Supervision authority changed");
        for (String role : Arrays.asList("supervisor", "server", "client", "intent")) checkAnchor(role);
        if (childIntentHash != null)
            require(childIntentHash.equals(hash(read(checkAnchor("intent")))), "Sealed child intent changed before effects");
    }

    /** Acquire both actual-child leases before sealing; no PID or free-port substitutes. */
    public synchronized JSONObject finish() throws Exception {
        require(supervisorOwned, "Cleanup requires the supervisor lease");
        if (!closed) { acquire("server"); acquire("client"); closed = true; }
        for (String role : Arrays.asList("supervisor", "server", "client", "intent")) checkAnchor(role);
        require(hash(read(privateFile(authorityPath))).equals(authorityHash), "Supervision authority changed");
        JSONObject intent = intent();
        Path credential = workspace.resolve("execution/credential.json");
        validateCredential(intent, credential);
        JSONObject revocation = record("current-base-verifier-revocation");
        revocation.put("intentSha256", intentHash);
        Path sealed = control.resolve("revocation.json");
        if (Files.exists(sealed, LinkOption.NOFOLLOW_LINKS)) {
            JSONObject prior = object(read(privateFile(sealed)));
            keys(prior, "schemaVersion", "manifestType", "invocationId", "supervisionSha256", "invocationSha256", "intentSha256");
            require(prior.similar(revocation), "Existing revocation is inconsistent");
        } else create(sealed, encode(revocation));
        if (Files.exists(credential, LinkOption.NOFOLLOW_LINKS)) {
            validateCredential(intent, credential);
            Files.delete(credential); syncDirectory(credential.getParent());
        }
        JSONObject result = new JSONObject();
        result.put("invocationId", authority.getString("invocationId"));
        result.put("supervisionSha256", authorityHash);
        result.put("invocationSha256", authority.getString("invocationSha256"));
        result.put("intentSha256", intentHash);
        result.put("revocationSha256", hash(read(sealed)));
        result.put("closed", true);
        return result;
    }

    public synchronized JSONObject recover(Path output) throws Exception {
        validateOutput(output);
        JSONObject result = finish();
        result.remove("closed"); result.put("schemaVersion", 1);
        result.put("manifestType", "current-base-verifier-recovery-evidence"); result.put("status", "closed");
        result.put("verifierContractSha256", authority.getString("verifierContractSha256"));
        result.put("credentialDeleted", true);
        create(output, encode(result));
        return result;
    }

    public void publish(Path output, JSONObject value) throws Exception {
        require(closed, "Success requires permanent invocation closure");
        validateOutput(output); create(output, encode(value));
    }

    public void validateOutput(Path output) throws Exception {
        require(!Files.exists(output, LinkOption.NOFOLLOW_LINKS), "Evidence output already exists");
        directory(output.getParent());
        disjoint(output, control); disjoint(output, workspace);
        JSONObject inputs = authority.getJSONObject("inputPaths");
        for (String name : INPUTS) disjoint(output, path(inputs.getString(name)));
    }

    private JSONObject intent() throws Exception {
        byte[] bytes = read(checkAnchor("intent"));
        intentHash = bytes.length == 0 ? "" : hash(bytes);
        if (bytes.length == 0) return null;
        JSONObject value = object(bytes);
        keys(value, "schemaVersion", "manifestType", "invocationId", "supervisionSha256", "invocationSha256",
            "state", "nonce", "credential");
        boundRecord(value, "current-base-verifier-intent");
        require("open".equals(value.getString("state")), "Intent state differs"); hashValue(value.getString("nonce"));
        JSONObject credential = value.getJSONObject("credential");
        keys(credential, "relativePath", "sha256", "size", "device", "inode");
        require("execution/credential.json".equals(credential.getString("relativePath")), "Credential path differs");
        hashValue(credential.getString("sha256"));
        require(credential.opt("size") instanceof Integer && credential.getInt("size") > 0
            && credential.getInt("size") <= 65536, "Credential size invalid");
        decimal(credential.getString("device")); decimal(credential.getString("inode"));
        return value;
    }

    private void validateCredential(JSONObject intent, Path credential) throws Exception {
        if (!Files.exists(credential, LinkOption.NOFOLLOW_LINKS)) return;
        require(intent != null, "Credential ownership was not durably sealed");
        JSONObject expected = intent.getJSONObject("credential");
        privateFile(credential); compareIdentity(credential, expected);
        require(Files.size(credential) == expected.getLong("size") && hash(read(credential)).equals(expected.getString("sha256")),
            "Credential contents differ from sealed ownership");
    }

    private JSONObject record(String type) {
        JSONObject value = new JSONObject(); value.put("schemaVersion", 1); value.put("manifestType", type);
        value.put("invocationId", authority.getString("invocationId"));
        value.put("supervisionSha256", authorityHash); value.put("invocationSha256", authority.getString("invocationSha256"));
        return value;
    }

    private void boundRecord(JSONObject value, String type) throws Exception {
        identity(value, type);
        for (String name : Arrays.asList("invocationId", "invocationSha256"))
            require(authority.getString(name).equals(value.getString(name)), "Intent invocation binding differs");
        require(authorityHash.equals(value.getString("supervisionSha256")), "Intent authority binding differs");
    }

    private Path checkAnchor(String role) throws Exception {
        Path file = privateFile(control.resolve(role.equals("intent") ? "intent.json" : role + ".lock"));
        JSONObject expected = authority.getJSONObject("files").getJSONObject(role);
        keys(expected, "device", "inode"); compareIdentity(file, expected);
        require(role.equals("intent") || Files.size(file) == 0, "Lease anchor is not empty");
        return file;
    }

    private void acquire(String role) throws Exception {
        Path file = checkAnchor(role);
        FileChannel channel = FileChannel.open(file, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS);
        FileLock lock = null;
        try {
            try { lock = channel.tryLock(); } catch (OverlappingFileLockException busy) { throw new Busy(); }
            if (lock == null) throw new Busy();
            checkAnchor(role);
            synchronized (CHANNELS) { CHANNELS.add(channel); LOCKS.add(lock); }
        } catch (Exception failure) { if (lock != null) lock.release(); channel.close(); throw failure; }
    }

    public static Map<String,String> options(String[] arguments, String... names) throws Exception {
        Map<String,String> result = new TreeMap<>();
        require(arguments.length == names.length * 2, "Closed invocation argument count differs");
        for (int index = 0; index < arguments.length; index += 2) {
            require(arguments[index].startsWith("--"), "Malformed option");
            require(result.put(arguments[index].substring(2), arguments[index + 1]) == null, "Duplicate option");
        }
        require(result.keySet().equals(new HashSet<>(Arrays.asList(names))), "Closed invocation options differ");
        return result;
    }

    public static String invocationHash(Map<String,String> options) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        for (Map.Entry<String,String> entry : new TreeMap<>(options).entrySet()) {
            if (entry.getKey().equals("supervision") || entry.getKey().equals("supervision-sha256")) continue;
            digest.update(entry.getKey().getBytes(StandardCharsets.UTF_8)); digest.update((byte)0);
            digest.update(entry.getValue().getBytes(StandardCharsets.UTF_8)); digest.update((byte)0);
        }
        return hex(digest.digest());
    }

    public static Path path(String value) throws Exception {
        require(value != null && value.length() <= 4096 && value.indexOf('\0') < 0, "Missing or malformed path");
        Path path = Paths.get(value);
        require(path.isAbsolute() && path.normalize().equals(path), "Path must be canonical absolute");
        for (Path cursor = path; cursor != null; cursor = cursor.getParent())
            require(!Files.isSymbolicLink(cursor), "Symlink path component refused");
        return path;
    }
    private static Path directory(Path value) throws Exception {
        path(value.toString()); require(Files.isDirectory(value, LinkOption.NOFOLLOW_LINKS) && value.toRealPath().equals(value),
            "Directory is missing or noncanonical"); return value;
    }
    private static Path privateFile(Path value) throws Exception {
        path(value.toString()); require(Files.isRegularFile(value, LinkOption.NOFOLLOW_LINKS) && value.toRealPath().equals(value),
            "Private file is missing or noncanonical");
        require(((Number)Files.getAttribute(value, "unix:nlink", LinkOption.NOFOLLOW_LINKS)).longValue() == 1,
            "Private file is aliased");
        require(Files.getPosixFilePermissions(value).equals(PosixFilePermissions.fromString("rw-------")), "Private file mode differs");
        return value;
    }
    private static JSONObject fileIdentity(Path path) throws Exception {
        JSONObject value = new JSONObject();
        value.put("device", Files.getAttribute(path, "unix:dev", LinkOption.NOFOLLOW_LINKS).toString());
        value.put("inode", Files.getAttribute(path, "unix:ino", LinkOption.NOFOLLOW_LINKS).toString()); return value;
    }
    private static void compareIdentity(Path path, JSONObject expected) throws Exception {
        JSONObject actual = fileIdentity(path);
        for (String key : Arrays.asList("device", "inode"))
            require(decimal(expected.getString(key)).equals(actual.getString(key)), "Prebound file inode was replaced");
    }
    private static String decimal(String value) throws Exception {
        require(value.matches("0|[1-9][0-9]{0,19}"), "File identity is not canonical decimal"); return value;
    }
    private static void disjoint(Path first, Path second) throws Exception {
        require(!first.startsWith(second) && !second.startsWith(first), "Paths must be disjoint from every supplied input");
    }
    public static byte[] read(Path file) throws Exception {
        ByteBuffer buffer = ByteBuffer.allocate(65537);
        try (FileChannel channel = FileChannel.open(file, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
            while (buffer.hasRemaining() && channel.read(buffer) >= 0) { }
        }
        require(buffer.position() <= 65536, "Supervision document exceeds 64 KiB");
        return Arrays.copyOf(buffer.array(), buffer.position());
    }
    private static JSONObject object(byte[] bytes) throws Exception {
        return new JSONObject(new String(bytes, StandardCharsets.UTF_8));
    }
    private static byte[] encode(JSONObject value) { return (value.toString() + "\n").getBytes(StandardCharsets.UTF_8); }
    private static void keys(JSONObject value, String... names) throws Exception {
        require(value.keySet().equals(new HashSet<>(Arrays.asList(names))), "Closed supervision object fields differ");
    }
    private static void identity(JSONObject value, String type) throws Exception {
        require(value.opt("schemaVersion") instanceof Integer && value.getInt("schemaVersion") == 1
            && type.equals(value.getString("manifestType")), "Supervision identity differs");
    }
    private static String hashValue(String value) throws Exception {
        require(value != null && value.matches("[0-9a-f]{64}"), "SHA256 binding is invalid"); return value;
    }
    public static String hash(byte[] bytes) throws Exception { return hex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
    private static String hex(byte[] bytes) {
        StringBuilder value = new StringBuilder(); for (byte part : bytes) value.append(String.format("%02x", part & 255)); return value.toString();
    }
    private static void writeEmpty(Path file, byte[] bytes) throws Exception {
        privateFile(file); require(Files.size(file) == 0, "Refusing to overwrite a supervision file");
        try (FileChannel channel = FileChannel.open(file, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
            ByteBuffer buffer = ByteBuffer.wrap(bytes); while (buffer.hasRemaining()) channel.write(buffer); channel.force(true);
        }
    }
    private static void create(Path file, byte[] bytes) throws Exception {
        Files.createFile(file, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
        writeEmpty(file, bytes); syncDirectory(file.getParent());
    }
    public static void syncDirectory(Path directory) throws Exception {
        try (FileChannel channel = FileChannel.open(directory, StandardOpenOption.READ)) { channel.force(true); }
    }
    private static void require(boolean condition, String message) throws IOException {
        if (!condition) throw new IOException(message);
    }
}

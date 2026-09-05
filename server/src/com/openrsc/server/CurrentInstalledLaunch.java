package com.openrsc.server;

import org.json.JSONObject;
import org.json.JSONArray;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.*;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Closed POSIX installed-process bootstrap. Deliberately has no game/logging
 * dependency: validation and the JVM-owned lease precede game initialization.
 * The peer copy is kept identical (apart from package) by a regression test.
 */
public final class CurrentInstalledLaunch {
    private static volatile CurrentInstalledLaunch current;
    private final JSONObject document;
    private final Path descriptor;
    private final String descriptorHash;
    private final String role;
    private final FileChannel leaseChannel;
    private final FileLock lease;
    private final RSAPublicKey publicKey;
    private Path sessionDirectory;
    private String nonce;
    private volatile boolean ready;
    private volatile boolean windowShown;
    private CurrentInstalledLaunch(JSONObject value, Path descriptor, String role,
                                   FileChannel channel, FileLock lease) throws Exception {
        this.document = value; this.descriptor = descriptor; this.role = role;
        this.descriptorHash = sha256(descriptor);
        this.leaseChannel = channel; this.lease = lease;
        String pem = new String(Files.readAllBytes(bound("publicKey")), java.nio.charset.StandardCharsets.US_ASCII);
        byte[] encoded = Base64.getMimeDecoder().decode(pem.replace("-----BEGIN PUBLIC KEY-----", "")
            .replace("-----END PUBLIC KEY-----", ""));
        publicKey = (RSAPublicKey) KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(encoded));
        if ("server".equals(role)) {
            Path privateFile = regular(root("sideStateRoot").resolve("server.pem"));
            if (Files.size(privateFile) > 65536) throw new IOException("Private key exceeds 64 KiB");
            if (!Files.getPosixFilePermissions(privateFile).equals(PosixFilePermissions.fromString("rw-------")))
                throw new IOException("Installed server private key must have mode 0600");
            String privatePem = new String(Files.readAllBytes(privateFile), java.nio.charset.StandardCharsets.US_ASCII);
            byte[] privateEncoded = Base64.getMimeDecoder().decode(privatePem.replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", ""));
            PrivateKey privateKey = KeyFactory.getInstance("RSA").generatePrivate(
                new java.security.spec.PKCS8EncodedKeySpec(privateEncoded));
            Signature signature = Signature.getInstance("SHA256withRSA");
            byte[] challenge = new byte[32]; new SecureRandom().nextBytes(challenge);
            signature.initSign(privateKey); signature.update(challenge); byte[] proof = signature.sign();
            signature.initVerify(publicKey); signature.update(challenge);
            if (!signature.verify(proof)) throw new IOException("Installed server key pair does not match");
        }
    }

    public static CurrentInstalledLaunch open(String[] args, String role, Class<?> anchor) throws Exception {
        if (current != null || args.length != 2 || !"--launch".equals(args[0])
            || !Arrays.asList("server", "client").contains(role)) throw new IOException("Exact --launch descriptor required");
        if (!FileSystems.getDefault().supportedFileAttributeViews().contains("posix"))
            throw new IOException("Installed Current Base launch requires POSIX");
        for (String key : System.getProperties().stringPropertyNames())
            if (key.startsWith("openrsc.") || key.startsWith("spoiledmilk.")
                || key.equals("conf") || key.equals("log4j.configurationFile"))
                throw new IOException("External runtime property is not admitted: " + key);
        for (String key : System.getenv().keySet())
            if (key.startsWith("OPENRSC_") || key.startsWith("SPOILED_MILK_")
                || Arrays.asList("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH").contains(key))
                throw new IOException("External runtime environment override is not admitted: " + key);
        Path descriptor = regular(Paths.get(args[1]));
        JSONObject value = object(descriptor);
        keys(value, "schemaVersion", "manifestType", "role", "installationId",
            "compositionIdentity", "runtimeProfile", "installedMapProfile", "mapRoot", "mapPackageFingerprintSha256",
            "codeRoot", "codeTreeSha256", "workingRoot", "stateRoot", "sideStateRoot",
            "installationRoot", "sessionRoot", "configuration", "endpoint", "publicKey");
        if (!(value.opt("schemaVersion") instanceof Integer) || value.getInt("schemaVersion") != 1
            || !"current-base-installed-launch".equals(value.getString("manifestType"))
            || !role.equals(value.getString("role"))) throw new IOException("Unsupported launch identity");
        if (!UUID.fromString(value.getString("installationId")).toString().equals(value.getString("installationId")))
            throw new IOException("Invalid installation identity");
        List<Path> roots = new ArrayList<Path>();
        for (String key : Arrays.asList("codeRoot", "workingRoot", "stateRoot", "sideStateRoot", "mapRoot")) {
            Path path = directory(Paths.get(value.getString(key)));
            for (Path previous : roots) {
                if ("sideStateRoot".equals(key) && previous.equals(roots.get(2)) && path.startsWith(previous)) continue;
                disjoint(path, previous);
            }
            roots.add(path);
        }
        Path installation = directory(Paths.get(value.getString("installationRoot")));
        Path working = roots.get(1);
        if (!working.equals(Paths.get("").toRealPath())) throw new IOException("Process cwd differs from reviewed working root");
        for (String key : Arrays.asList("stateRoot", "sideStateRoot", "workingRoot", "installationRoot"))
            privateDirectory(directory(Paths.get(value.getString(key))));
        Path session = directory(Paths.get(value.getString("sessionRoot")));
        privateDirectory(session);
        if (!session.equals(installation.resolve("sessions").resolve(role)))
            throw new IOException("Session parent differs from fixed installation role path");
        for (Path root : roots) disjoint(session, root);
        Path lock = regular(installation.resolve(role + ".lock"));
        if (Files.size(lock) != 0
            || !Files.getPosixFilePermissions(lock).equals(PosixFilePermissions.fromString("rw-------")))
            throw new IOException("Role lease file must be empty with mode 0600");
        Object lockKey = Files.readAttributes(lock, java.nio.file.attribute.BasicFileAttributes.class,
            LinkOption.NOFOLLOW_LINKS).fileKey();
        if (lockKey == null) throw new IOException("Role lease has no stable filesystem identity");
        FileChannel channel = FileChannel.open(lock, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS);
        FileLock lease = channel.tryLock();
        if (lease == null) { channel.close(); throw new IOException("Installation role is already leased"); }
        try {
            if (!lockKey.equals(Files.readAttributes(regular(lock), java.nio.file.attribute.BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS).fileKey())) throw new IOException("Role lease inode changed during acquisition");
            CurrentInstalledLaunch launch = new CurrentInstalledLaunch(value, descriptor, role, channel, lease);
            launch.validate(anchor);
            byte[] random = new byte[32]; new SecureRandom().nextBytes(random);
            launch.nonce = hex(random);
            launch.sessionDirectory = Files.createDirectory(session.resolve(launch.nonce),
                PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
            current = launch;
            System.out.println("INSTALLED_SESSION " + launch.nonce);
            Thread deadline = new Thread(() -> {
                long limit = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(120);
                try {
                    while (!launch.ready && System.nanoTime() < limit) Thread.sleep(100);
                    if (!launch.ready) {
                        System.err.println("Installed runtime readiness exceeded 120 seconds");
                        System.exit(2);
                    }
                } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
            }, "installed-readiness-deadline");
            deadline.setDaemon(true); deadline.start();
            // Never close the lease from a shutdown hook: other hooks can still save.
            // These strongly-held fields live until OS process teardown releases locks.
            return launch;
        } catch (Throwable failure) {
            lease.release(); channel.close(); throw failure;
        }
    }

    private void validate(Class<?> anchor) throws Exception {
        validateSelection();
        if (!sha256(descriptor).equals(descriptorHash)) throw new IOException("Launch descriptor changed during validation");
        Path code = root("codeRoot");
        if (!treeHash(code).equals(hash(document, "codeTreeSha256"))
            || !packageFingerprint(root("mapRoot")).equals(hash(document, "mapPackageFingerprintSha256")))
            throw new IOException("Installed code/map tree differs from reviewed launch");
        Path artifact = regular(Paths.get(anchor.getProtectionDomain().getCodeSource().getLocation().toURI()));
        String jar = role.equals("server") ? "core.jar" : "Open_RSC_Client.jar";
        if (!artifact.equals(code.resolve(jar))) throw new IOException("Bootstrap artifact is outside bound role code root");
        String classpath = artifact.toString() + (role.equals("server")
            ? java.io.File.pathSeparator + code.resolve("plugins.jar") : "");
        if (!System.getProperty("java.class.path").equals(classpath))
            throw new IOException("Additional executable classpath roots are not admitted");
        JSONObject identity = object(bound("compositionIdentity"));
        if (!identity.getBoolean("installable") || !"current-base-v1".equals(identity.getString("variantId")))
            throw new IOException("Installed launch requires installable Current Base");
        inventory(identity, role.equals("server") ? "server-runtime" : "client-runtime", artifact);
        inventory(identity, "runtime-profile", bound("runtimeProfile"));
        if (role.equals("server")) inventory(identity, "server-plugins", regular(code.resolve("plugins.jar")));
        JSONObject profile = object(bound("runtimeProfile"));
        if (!"current-base-v1".equals(profile.getString("variantId"))) throw new IOException("Wrong runtime profile");
        JSONObject map = object(bound("installedMapProfile"));
        keys(map, "schemaVersion", "manifestType", "active", "packageId", "packageVersion",
            "packageFingerprintSha256", "manifestSha256", "packageRelativePath");
        if (!map.getBoolean("active") || !("world-builder-installed-" + role + "-profile").equals(map.getString("manifestType"))
            || !sha256(regular(root("mapRoot").resolve("manifest.json"))).equals(hash(map, "manifestSha256"))
            || !hash(map, "packageFingerprintSha256").equals(hash(document, "mapPackageFingerprintSha256")))
            throw new IOException("Installed map profile is not exact");
        JSONObject endpoint = document.getJSONObject("endpoint");
        keys(endpoint, "host", "gamePort");
        String host = endpoint.getString("host");
        if (!host.matches("[A-Za-z0-9][A-Za-z0-9.:-]{0,252}")
            || !(endpoint.opt("gamePort") instanceof Integer) || endpoint.getInt("gamePort") < 1 || endpoint.getInt("gamePort") > 65535)
            throw new IOException("Invalid installed endpoint");
        if (role.equals("server")) {
            validateConfiguration(profile);
            Path database = regular(root("stateRoot").resolve("current_base.db"));
            if (!Files.getPosixFilePermissions(database).equals(PosixFilePermissions.fromString("rw-------")))
                throw new IOException("Installed database must have mode 0600");
            regular(root("sideStateRoot").resolve("server.pem"));
            if (!bound("publicKey").equals(root("sideStateRoot").resolve("client.pem")))
                throw new IOException("Server public key must belong to persistent side-state");
            for (String name : Arrays.asList("badwords.txt", "goodwords.txt", "alertwords.txt"))
                regular(root("sideStateRoot").resolve(name));
            for (String name : Arrays.asList("ipbans.txt", "ipbans.temp")) {
                Path file = root("sideStateRoot").resolve(name);
                if (Files.exists(file, LinkOption.NOFOLLOW_LINKS)) regular(file);
            }
        } else {
            keys(document.getJSONObject("configuration"));
            if (!bound("publicKey").equals(root("sideStateRoot").resolve("client.pem")))
                throw new IOException("Client public key must belong to its own persistent side-state");
            for (String name : Arrays.asList("clientSettings.conf", "uid.dat", "hideIp.txt", "credentials.txt")) {
                Path stateFile = root("sideStateRoot").resolve(name);
                if (Files.exists(stateFile, LinkOption.NOFOLLOW_LINKS)) {
                    regular(stateFile);
                    if ("credentials.txt".equals(name)
                        && !Files.getPosixFilePermissions(stateFile).equals(PosixFilePermissions.fromString("rw-------")))
                        throw new IOException("Remembered client credentials must have mode 0600");
                }
            }
        }
        // Working directories are disposable, not additional executable/configuration roots.
        try (java.util.stream.Stream<Path> paths = Files.walk(root("workingRoot"))) {
            List<Path> entries = paths.limit(30001).collect(Collectors.toList());
            if (entries.size() > 30000) throw new IOException("Working history exceeds entry bound");
            for (Path path : entries) {
                if (Files.isSymbolicLink(path)) throw new IOException("Working directory contains a symbolic link");
                if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) regular(path);
                String name = path.getFileName().toString().toLowerCase(Locale.ROOT);
                if (name.endsWith(".jar") || name.endsWith(".class") || name.endsWith(".conf") || name.endsWith(".pem"))
                    throw new IOException("Working directory contains an unreviewed executable/configuration input");
            }
        }
    }

    public void configure() throws Exception {
        validateSelection();
        System.setProperty("openrsc.currentCompositionIdentityFile", bound("compositionIdentity").toString());
        System.setProperty("openrsc.worldBuilderInstalledMapRoot", root("mapRoot").toString());
        System.setProperty("openrsc.worldBuilderInstalled" + (role.equals("server") ? "Server" : "Client") + "Profile",
            bound("installedMapProfile").toString());
        if (role.equals("server")) System.setProperty("openrsc.currentBaseStateRoot", root("stateRoot").toString());
        else {
            // Current Base ships no native renderer runtime. Its normal public
            // desktop uses the maintained software window, not undeclared JARs.
            System.setProperty("spoiledmilk.openglPresenter", "false");
            System.setProperty("spoiledmilk.openglInput", "false");
            System.setProperty("spoiledmilk.openglPrimaryWindow", "false");
            System.setProperty("spoiledmilk.directFramebuffer", "false");
            System.setProperty("spoiledmilk.skipLegacyWorldRaster", "false");
        }
    }

    public static CurrentInstalledLaunch current() { return current; }
    private void validateSelection() throws Exception {
        Path pointer = regular(root("installationRoot").resolve("active-launch.json"));
        if (!Files.getPosixFilePermissions(pointer).equals(PosixFilePermissions.fromString("rw-------")))
            throw new IOException("Active selection must have mode 0600");
        JSONObject active = object(pointer);
        keys(active, "schemaVersion", "manifestType", "installationId", "serverDescriptorSha256", "clientDescriptorSha256");
        if (!(active.opt("schemaVersion") instanceof Integer) || active.getInt("schemaVersion") != 1
            || !"current-base-installed-selection".equals(active.getString("manifestType"))
            || !document.getString("installationId").equals(active.getString("installationId"))
            || !descriptorHash.equals(hash(active, role + "DescriptorSha256"))
            || !descriptorHash.equals(sha256(descriptor)))
            throw new IOException("Launch descriptor is not the active installed role selection");
        hash(active, "serverDescriptorSha256"); hash(active, "clientDescriptorSha256");
    }
    private void validateConfiguration(JSONObject profile) throws Exception {
        Map<String, String> values = new HashMap<String, String>();
        for (String original : Files.readAllLines(bound("configuration"), java.nio.charset.StandardCharsets.UTF_8)) {
            String line = original.split("#", 2)[0].trim();
            if (line.isEmpty()) continue;
            int separator = line.indexOf(':');
            if (separator < 1) throw new IOException("Reviewed server configuration is malformed");
            String key = line.substring(0, separator).trim(), value = line.substring(separator + 1).trim();
            if (value.isEmpty()) continue;
            if (values.put(key, value) != null) throw new IOException("Reviewed server configuration repeats a key");
        }
        JSONObject excluded = profile.getJSONObject("advancedExclusions").getJSONObject("configuration");
        for (String key : excluded.keySet())
            if (!Boolean.FALSE.equals(excluded.opt(key)) || !"false".equals(values.get(key)))
                throw new IOException("Reviewed configuration does not exclude an Advanced setting");
        if (!"sqlite".equals(values.get("db_type")) || !"current_base".equals(values.get("db_name"))
            || !"false".equals(values.get("allow_in_game_world_editor"))
            || !"false".equals(values.get("want_feature_websockets"))
            || !Integer.toString(port()).equals(values.get("server_port")))
            throw new IOException("Reviewed configuration does not select the normal Current Base state/endpoint");
    }
    public static void signalWindowShown() { if (current != null) current.windowShown = true; }
    public boolean hasWindowShown() { return windowShown; }
    public Path root(String key) throws IOException { return directory(Paths.get(document.getString(key))); }
    public Path bound(String key) throws Exception {
        JSONObject entry = document.getJSONObject(key); keys(entry, "path", "sha256");
        Path path = regular(Paths.get(entry.getString("path")));
        if (Files.size(path) > ("publicKey".equals(key) ? 65536 : 1048576))
            throw new IOException("Bound descriptor input exceeds size limit");
        if (!sha256(path).equals(hash(entry, "sha256"))) throw new IOException("Bound input differs: " + key);
        return path;
    }
    public String host() { return document.getJSONObject("endpoint").getString("host"); }
    public int port() { return document.getJSONObject("endpoint").getInt("gamePort"); }
    public static Path sideState(String name) {
        try {
            if (current == null) return Paths.get(name);
            List<String> names = current.role.equals("server")
                ? Arrays.asList("server.pem", "client.pem", "badwords.txt", "goodwords.txt", "alertwords.txt", "ipbans.txt", "ipbans.temp")
                : Arrays.asList("client.pem", "clientSettings.conf", "uid.dat", "hideIp.txt", "credentials.txt");
            if (!names.contains(name)) throw new IOException("Side-state name is not admitted");
            Path root = current.root("sideStateRoot"), path = root.resolve(name).normalize();
            if (!path.startsWith(root) || path.equals(root)) throw new IOException("Side-state path escapes its declared root");
            if (Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
                regular(path);
                if (("credentials.txt".equals(name) || "server.pem".equals(name))
                    && !Files.getPosixFilePermissions(path).equals(PosixFilePermissions.fromString("rw-------")))
                    throw new IOException("Private side-state file must have mode 0600");
            }
            return path;
        } catch (IOException failure) { throw new IllegalStateException(failure); }
    }
    public static Path content(String relative) {
        try {
            return current == null ? Paths.get(relative) : current.root("codeRoot").resolve(relative);
        } catch (IOException failure) { throw new IllegalStateException(failure); }
    }
    public static java.io.OutputStream openSideStateOutput(String name) throws IOException {
        Path path = sideState(name);
        Set<OpenOption> options = new HashSet<OpenOption>(Arrays.asList(StandardOpenOption.WRITE,
            StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, LinkOption.NOFOLLOW_LINKS));
        return java.nio.channels.Channels.newOutputStream(Files.newByteChannel(path, options,
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------"))));
    }
    public void requirePublicKey(BigInteger exponent, BigInteger modulus) {
        if (!publicKey.getPublicExponent().equals(exponent) || !publicKey.getModulus().equals(modulus))
            throw new IllegalStateException("Server public key differs from installed trust binding");
    }

    public synchronized void ready() throws Exception {
        if (ready) throw new IOException("Readiness already published");
        writeNew(sessionDirectory.resolve("ready.json"), binding("ready"));
        ready = true;
    }
    public boolean shutdownRequested() throws Exception {
        Path request = sessionDirectory.resolve("shutdown.json");
        if (!Files.exists(request, LinkOption.NOFOLLOW_LINKS)) return false;
        JSONObject actual = object(regular(request));
        JSONObject expected = binding("shutdown");
        if (!actual.similar(expected)) throw new IOException("Shutdown request is not bound to this live session");
        return true;
    }
    private JSONObject binding(String action) throws Exception {
        return new JSONObject().put("schemaVersion", 1).put("manifestType", "current-base-installed-session")
            .put("action", action).put("installationId", document.getString("installationId")).put("role", role)
            .put("nonce", nonce).put("descriptorSha256", descriptorHash)
            .put("compositionIdentitySha256", hash(document.getJSONObject("compositionIdentity"), "sha256"))
            .put("mapManifestSha256", hash(object(bound("installedMapProfile")), "manifestSha256"));
    }
    private static void writeNew(Path file, JSONObject value) throws Exception {
        Path temporary = Files.createTempFile(file.getParent(), ".session-", ".tmp",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
        try {
            Files.write(temporary, (value.toString(2) + "\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));
            // No replacement. Atomic publication under the private session directory.
            Files.createLink(file, temporary);
        } finally { Files.deleteIfExists(temporary); }
    }
    public static Path directory(Path path) throws IOException {
        if (!path.isAbsolute() || !path.equals(path.normalize()) || !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
            || !path.equals(path.toRealPath())) throw new IOException("Directory must be canonical and absolute");
        return path;
    }
    public static Path regular(Path path) throws IOException {
        if (!path.isAbsolute() || !path.equals(path.normalize()) || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
            || !path.equals(path.toRealPath()) || ((Number) Files.getAttribute(path, "unix:nlink")).intValue() != 1)
            throw new IOException("File must be canonical, absolute, regular and singly linked");
        return path;
    }
    private static void privateDirectory(Path path) throws IOException {
        if (!Files.getPosixFilePermissions(path).equals(PosixFilePermissions.fromString("rwx------")))
            throw new IOException("Mutable installed roots must have mode 0700");
    }
    private static void disjoint(Path first, Path second) throws IOException {
        if (first.startsWith(second) || second.startsWith(first)) throw new IOException("Installed roots overlap");
    }
    private static JSONObject object(Path path) throws IOException {
        if (Files.size(path) > 1024 * 1024) throw new IOException("Descriptor is too large");
        return new JSONObject(new String(Files.readAllBytes(path), java.nio.charset.StandardCharsets.UTF_8));
    }
    private static void keys(JSONObject value, String... expected) throws IOException {
        if (!new TreeSet<String>(value.keySet()).equals(new TreeSet<String>(Arrays.asList(expected))))
            throw new IOException("Closed descriptor fields differ");
    }
    private static String hash(JSONObject value, String key) throws IOException {
        String result = value.getString(key);
        if (!result.matches("[0-9a-f]{64}")) throw new IOException("Invalid SHA-256");
        return result;
    }
    private static void inventory(JSONObject identity, String role, Path path) throws Exception {
        JSONArray rows = identity.getJSONArray("bundleInventory");
        int count = 0;
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.getJSONObject(i);
            if (role.equals(row.getString("role"))) {
                count++;
                if (!sha256(path).equals(hash(row, "sha256"))) throw new IOException("Artifact inventory mismatch: " + role);
            }
        }
        if (count != 1) throw new IOException("Artifact role is missing or repeated: " + role);
    }
    public static String treeHash(Path root) throws Exception { return treeDigest(root, false); }
    public static String packageFingerprint(Path root) throws Exception { return treeDigest(root, true); }
    private static String treeDigest(Path root, boolean packageIdentity) throws Exception {
        List<Path> files;
        try (java.util.stream.Stream<Path> stream = Files.walk(root)) {
            files = stream.limit(30001).collect(Collectors.toList());
        }
        if (files.size() > 30000) throw new IOException("Tree exceeds entry bound");
        List<Path> regular = new ArrayList<Path>();
        long size = 0;
        for (Path path : files) {
            if (Files.isSymbolicLink(path)) throw new IOException("Tree contains a symbolic link");
            if (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) continue;
            regular(path); regular.add(path); size += Files.size(path);
        }
        if (regular.size() > 20000 || size > 1073741824L) throw new IOException("Tree exceeds input bound");
        Collections.sort(regular, Comparator.comparing(path -> root.relativize(path).toString().replace('\\', '/')));
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        for (Path file : regular) {
            String record = root.relativize(file).toString().replace('\\', '/') + "\0"
                + (packageIdentity ? Files.size(file) + "\0" : "") + sha256(file) + (packageIdentity ? "\n" : "\0");
            digest.update(record.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        }
        return hex(digest.digest());
    }
    public static String sha256(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(path)) {
            byte[] bytes = new byte[65536]; int count;
            while ((count = input.read(bytes)) >= 0) digest.update(bytes, 0, count);
        }
        return hex(digest.digest());
    }
    private static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte value : bytes) result.append(String.format(Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }
}

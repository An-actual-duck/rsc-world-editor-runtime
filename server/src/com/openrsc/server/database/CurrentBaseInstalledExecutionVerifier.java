package com.openrsc.server.database;

import com.openrsc.server.io.AdaptiveWorldBuilderPackageGuard;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.awt.GraphicsEnvironment;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Executes a copied installed Current Base pair twice against copied SQLite
 * state. Source roots and all supplied inputs are hashed before and after and
 * are never passed to a child runtime as writable state.
 */
public final class CurrentBaseInstalledExecutionVerifier {
	private static final String CONTRACT_SHA256 =
		"f63d54f671033c19fdc525c067641cab456022c51feca06f6d21fad2e3a56ef9";
	private static final int MAX_LOG_BYTES = 1048576;
	private static final int MAX_MAP_MANIFEST_BYTES = 16777216;
	private static final int MAX_SOURCE_FILES = 20000;
	private static final long MAX_SOURCE_BYTES = 1073741824L;
	private static final Set<String> OPTIONS = set("contract", "composition-identity",
		"runtime-profile", "installed-server-root", "installed-client-root",
		"server-config", "server-profile", "client-profile", "map-package", "state-db",
		"workspace", "server-port", "websocket-port", "evidence");
	private static final List<String> IDENTITY_FIELDS = Arrays.asList(
		"platformReleaseId", "platformManifestHash", "variantId", "variantManifestHash",
		"moduleSetHash", "bundleInventoryHash");
	private static final Pattern HASH = Pattern.compile("[0-9a-f]{64}");
	private static final Pattern MARKER = Pattern.compile(
		"CURRENT_BASE_RUNTIME_EXECUTION variant=(\\S+) canonicalMap=true initialRegion=true "
		+ "worldX=(-?\\d+) worldY=(-?\\d+) coins=(\\d+) prayer=(\\d+) magic=(\\d+) "
		+ "woodcut=(\\d+) quest1=(\\d+) clientAdvanced=false");
	private static final SecureRandom RANDOM = new SecureRandom();

	private CurrentBaseInstalledExecutionVerifier() { }

	public static void main(String[] arguments) {
		Map<String,String> parsed = null;
		try {
			Map<String,String> options = options(arguments); parsed = options;
			if (!options.keySet().equals(OPTIONS)) throw new IOException(
				"arguments differ from the closed installed-execution invocation");
			Contract contract = Contract.load(regular(options, "contract"));
			Verification verification = new Verification(options, contract);
			JSONObject evidence = verification.execute();
			Path output = newOutput(options, "evidence");
			Files.createDirectories(output.getParent());
			Files.write(output, (evidence.toString(2) + "\n").getBytes(StandardCharsets.UTF_8),
				StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
			System.out.println("Current Base installed execution verified");
		} catch (Exception failure) {
			System.err.println("Current Base installed execution refused: "
				+ safeMessage(failure, parsed));
			System.exit(2);
		}
	}

	private static final class Verification {
		private final Map<String,String> options;
		private final Contract contract;
		private final List<BoundedProcess> children = new ArrayList<BoundedProcess>();
		private final JSONArray logs = new JSONArray();
		private final JSONArray runs = new JSONArray();
		private Path workspace, serverRoot, clientRoot, workingState, credential;
		private JSONObject identity;
		private String sourceServerBefore, sourceClientBefore, inputsBefore;
		private String mapFingerprint, username, password;
		private int accountId, x, y, coins, prayer, magic, woodcut, questStage;

		private Verification(Map<String,String> options, Contract contract) {
			this.options = options; this.contract = contract;
		}

		private JSONObject execute() throws Exception {
			Path sourceServer = directory(options, "installed-server-root");
			Path sourceClient = directory(options, "installed-client-root");
			Path identityPath = regular(options, "composition-identity");
			Path runtimeProfile = regular(options, "runtime-profile");
			Path serverConfig = regular(options, "server-config");
			Path serverProfile = regular(options, "server-profile");
			Path clientProfile = regular(options, "client-profile");
			Path mapPackage = directory(options, "map-package");
			Path state = regular(options, "state-db");
			requireNoSqliteSidecars(state);
			workspace = newDirectory(options, "workspace");
			Path evidence = newOutput(options, "evidence");
			Path[] inputs = {sourceServer, sourceClient, identityPath, runtimeProfile,
				serverConfig, serverProfile, clientProfile, mapPackage, state,
				regular(options, "contract")};
			requireDisjoint(workspace, "execution workspace", inputs);
			requireDisjoint(evidence, "evidence", inputs);
			requireDisjoint(workspace, "execution workspace", evidence);
			requireGraphicalEnvironment();
			int serverPort = port(options, "server-port");
			int websocketPort = port(options, "websocket-port");
			if (serverPort == websocketPort) throw new IOException("loopback ports must differ");
			sourceServerBefore = treeHash(sourceServer);
			sourceClientBefore = treeHash(sourceClient);
			Map<String,String> connections = config(sourceServer.resolve("connections.conf"));
			if (!"sqlite".equals(connections.get("db_type"))) throw new IOException(
				"installed server connections.conf must select sqlite");
			inputsBefore = inputSetHash(identityPath, runtimeProfile, serverConfig,
				serverProfile, clientProfile, mapPackage, state);
			identity = object(identityPath, "composition identity");
			validateIdentity(identity);
			requireInventoryHash(identity, "server-runtime", sourceServer.resolve("core.jar"));
			requireInventoryHash(identity, "server-plugins", sourceServer.resolve("plugins.jar"));
			requireInventoryHash(identity, "client-runtime",
				sourceClient.resolve("Open_RSC_Client.jar"));
			requireInventoryHash(identity, "runtime-profile", runtimeProfile);
			requireInventoryHash(identity, "installed-execution-verifier",
				regular(options, "contract"));
			JSONObject profile = object(runtimeProfile, "runtime profile");
			validateRuntimeProfile(profile, serverConfig);
			JSONObject serverInstalled = object(serverProfile, "server installed profile");
			JSONObject clientInstalled = object(clientProfile, "client installed profile");
			String packageRelative = installedPackageRelative(serverInstalled, "server");
			if (!packageRelative.equals(installedPackageRelative(clientInstalled, "client")))
				throw new IOException("server/client installed profiles select different maps");
			mapFingerprint = AdaptiveWorldBuilderPackageGuard
				.requireClosedPackage(mapPackage).getFingerprint();
			if (!mapFingerprint.equals(serverInstalled.getString("packageFingerprintSha256"))
				|| !mapFingerprint.equals(clientInstalled.getString("packageFingerprintSha256")))
				throw new IOException("installed profiles do not bind the supplied map package");
			int[] coordinate = mapCoordinate(mapPackage);
			x = coordinate[0]; y = coordinate[1];

			createPrivateDirectory(workspace);
			serverRoot = workspace.resolve("execution/server");
			clientRoot = workspace.resolve("execution/client");
			copyTree(sourceServer, serverRoot);
			copyTree(sourceClient, clientRoot);
			Files.deleteIfExists(serverRoot.resolve("local.conf"));
			writeVerificationConnections(serverRoot.resolve("connections.conf"));
			Path renderedConfig = serverRoot.resolve("current-base.conf");
			copyFile(serverConfig, renderedConfig);
			renderVerificationConfig(renderedConfig, serverPort, websocketPort);
			copyFile(serverProfile, serverRoot.resolve("world-builder-configs/installed-server.json"));
			copyFile(clientProfile, clientRoot.resolve("world-builder-configs/installed-client.json"));
			Path relative = safeRelative(packageRelative);
			replaceTree(mapPackage, serverRoot.resolve(relative));
			replaceTree(mapPackage, clientRoot.resolve(relative));
			Path stateRoot = workspace.resolve("state");
			createPrivateDirectory(stateRoot);
			workingState = stateRoot.resolve("current_base.db");
			copyFile(state, workingState);
			setOwnerOnly(workingState, false);
			Path identityCopy = workspace.resolve("composition-identity.json");
			copyFile(identityPath, identityCopy);
			credential = workspace.resolve("execution/credential.json");
			String workingSeeded;
			try {
				seedDisposableAccount();
				workingSeeded = sha256(workingState);
				writeCredential();
				for (int run = 1; run <= 2; run++)
					runCycle(run, identityCopy, serverPort, websocketPort);
			} finally {
				for (BoundedProcess child : children) child.closeQuietly();
				children.clear();
				if (credential != null) Files.deleteIfExists(credential);
			}
			verifyPersistentState();
			String workingFinal = sha256(workingState);
			if (workingSeeded.equals(workingFinal)) throw new IOException(
				"disposable state did not record runtime execution changes");
			String sourceServerAfter = treeHash(sourceServer);
			String sourceClientAfter = treeHash(sourceClient);
			String inputsAfter = inputSetHash(identityPath, runtimeProfile, serverConfig,
				serverProfile, clientProfile, mapPackage, state);
			requireNoSqliteSidecars(state);
			if (!sourceServerBefore.equals(sourceServerAfter)
				|| !sourceClientBefore.equals(sourceClientAfter)
				|| !inputsBefore.equals(inputsAfter)) throw new IOException(
				"installed source or supplied verification input changed");
			if (Files.exists(credential, LinkOption.NOFOLLOW_LINKS)) throw new IOException(
				"disposable credential was not deleted");
			return evidence(sourceServerAfter, sourceClientAfter, inputsAfter,
				workingSeeded, workingFinal, serverPort, websocketPort);
		}

		private void runCycle(int run, Path identityPath, int serverPort,
			int websocketPort) throws Exception {
			BoundedProcess server = null, client = null;
			try {
				List<String> serverCommand = Arrays.asList(javaCommand(), "-Xms128m", "-Xmx768m",
					"-Dopenrsc.currentBaseStateRoot=" + workingState.getParent(),
					"-Dopenrsc.currentCompositionIdentityFile=" + identityPath,
					"-Dopenrsc.worldBuilderInstalledServerProfile="
						+ serverRoot.resolve("world-builder-configs/installed-server.json"),
					"-cp", "core.jar" + java.io.File.pathSeparator + "plugins.jar",
					"com.openrsc.server.Server", "current-base.conf");
				server = BoundedProcess.start(serverCommand, serverRoot,
					workspace.resolve("logs/server-" + run + ".log"));
				children.add(server);
				server.awaitText("Game world is now online on", 60, "server startup");

				List<String> clientCommand = Arrays.asList(javaCommand(), "-Xms256m", "-Xmx1024m",
					"-Dopenrsc.currentCompositionIdentityFile=" + identityPath,
					"-Dopenrsc.worldBuilderInstalledClientProfile="
						+ clientRoot.resolve("world-builder-configs/installed-client.json"),
					"-Dopenrsc.currentBaseExecutionEvidence=true",
					"-Dopenrsc.currentBaseHost=127.0.0.1",
					"-Dopenrsc.currentBasePort=" + serverPort,
					"-Dopenrsc.currentBaseCredentialFile=" + credential,
					"-Dsun.java2d.opengl=false", "-jar", "Open_RSC_Client.jar");
				client = BoundedProcess.start(clientCommand, clientRoot,
					workspace.resolve("logs/client-" + run + ".log"));
				children.add(client);
				String marker = client.awaitText("CURRENT_BASE_RUNTIME_EXECUTION", 90,
					"client evidence");
				if (!client.waitFor(20) || client.exitValue() != 0) throw new IOException(
					"client evidence process did not exit successfully");
				client.close();
				String serverText = server.awaitText("Unregistered " + username
					+ " from player list.", 20, "normal logout");
				if (!serverText.contains("Current composition handshake accepted")
					|| !serverText.contains("variant=current-base-v1")
					|| !serverText.contains("Connected to private external Current Base SQLite state")
					|| !serverText.contains("Processed login request for " + username
						+ " response: 64")) throw new IOException(
					"server did not record handshake and successful normal login");
				JSONObject observation = parseMarker(marker, run);
				awaitPersistentState(server);
				server.close();
				verifyPersistentState();
				observation.put("logoutPersisted", true);
				runs.put(observation);
				logs.put(server.logRecord(run, "server"));
				logs.put(client.logRecord(run, "client"));
			} finally {
				if (client != null) { client.closeQuietly(); children.remove(client); }
				if (server != null) { server.closeQuietly(); children.remove(server); }
			}
		}

		private JSONObject parseMarker(String text, int run) throws IOException {
			Matcher match = MARKER.matcher(text);
			if (!match.find()) throw new IOException("client runtime evidence marker is malformed");
			int observedX = integer(match.group(2)), observedY = integer(match.group(3));
			int observedCoins = integer(match.group(4)), observedPrayer = integer(match.group(5));
			int observedMagic = integer(match.group(6)), observedWoodcut = integer(match.group(7));
			int observedQuest = integer(match.group(8));
			if (!"current-base-v1".equals(match.group(1)) || observedX != x || observedY != y
				|| observedCoins != coins || observedPrayer != prayer || observedMagic != magic
				|| observedWoodcut != woodcut || observedQuest != questStage) throw new IOException(
				"client runtime evidence differs from generated disposable state");
			JSONObject row = new JSONObject();
			row.put("run", run); row.put("handshakeAccepted", true);
			row.put("loginAccepted", true); row.put("canonicalMap", true);
			row.put("initialRegion", true); row.put("worldX", observedX);
			row.put("worldY", observedY); row.put("coins", observedCoins);
			row.put("prayer", observedPrayer); row.put("magic", observedMagic);
			row.put("woodcut", observedWoodcut); row.put("questStage", observedQuest);
			row.put("advancedExcluded", true);
			return row;
		}

		private void seedDisposableAccount() throws Exception {
			Class.forName("org.sqlite.JDBC");
			try (Connection database = DriverManager.getConnection(
				"jdbc:sqlite:" + workingState.toUri().toASCIIString() + "?mode=rw")) {
				database.setAutoCommit(false);
				try {
					accountId = scalar(database, "SELECT COALESCE(MAX(id),0)+1 FROM players");
					int itemId = scalar(database,
						"SELECT COALESCE(MAX(itemID),0)+1 FROM itemstatuses");
					username = uniqueUsername(database);
					password = randomText(20, "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789");
					coins = 101 + accountId % 791; prayer = 11 + accountId % 5;
					magic = 16 + accountId % 5; woodcut = 21 + accountId % 5;
					questStage = 2 + accountId % 3;
					try (PreparedStatement statement = database.prepareStatement(
						"INSERT INTO players(id,username,pass,salt,x,y,quest_points,login_date) "
						+ "VALUES(?,?,?,?,?,?,?,?)")) {
						statement.setInt(1, accountId); statement.setString(2, username);
						statement.setString(3, password); statement.setString(4, "");
						statement.setInt(5, x); statement.setInt(6, y);
						statement.setInt(7, 0); statement.setInt(8, 100); statement.executeUpdate();
					}
					for (String table : Arrays.asList("curstats", "maxstats", "experience",
						"capped_experience")) try (PreparedStatement statement = database.prepareStatement(
						"INSERT INTO " + table + "(playerID,prayer,magic,woodcut,summoning) "
						+ "VALUES(?,?,?,?,?)")) {
						statement.setInt(1, accountId); statement.setInt(2, prayer);
						statement.setInt(3, magic); statement.setInt(4, woodcut);
						statement.setInt(5, table.startsWith("capped") || table.equals("experience") ? 0 : 1);
						statement.executeUpdate();
					}
					try (PreparedStatement statement = database.prepareStatement(
						"INSERT INTO itemstatuses(itemID,catalogID,amount,noted,wielded,durability) "
						+ "VALUES(?,10,?,0,0,0)")) {
						statement.setInt(1, itemId); statement.setInt(2, coins); statement.executeUpdate();
					}
					update(database, "INSERT INTO invitems(playerID,itemID,slot) VALUES(?,?,0)", accountId, itemId);
					update(database, "INSERT INTO quests(playerID,id,stage) VALUES(?,1,?)", accountId, questStage);
					try (PreparedStatement statement = database.prepareStatement(
						"INSERT INTO player_cache(playerID,type,`key`,`value`) VALUES(?,0,?,?)")) {
						statement.setInt(1, accountId); statement.setString(2, "current_base_verifier");
						statement.setString(3, Integer.toString(coins)); statement.executeUpdate();
					}
					try (PreparedStatement statement = database.prepareStatement(
						"INSERT INTO ironman(playerID,iron_man,iron_man_restriction,hc_ironman_death) "
						+ "VALUES(?,0,1,0)")) { statement.setInt(1, accountId); statement.executeUpdate(); }
					database.commit();
				} catch (Exception failure) { database.rollback(); throw failure; }
			}
		}

		private void awaitPersistentState(BoundedProcess server) throws Exception {
			long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
			Exception last = null;
			do {
				if (!server.process.isAlive()) throw new IOException(
					"server exited before normal logout persistence was verified");
				try { verifyPersistentState(); return; }
				catch (IOException | java.sql.SQLException pending) { last = pending; }
				Thread.sleep(50L);
			} while (System.nanoTime() < deadline);
			throw new IOException("normal logout persistence did not complete within its bound", last);
		}

		private void verifyPersistentState() throws Exception {
			try (Connection database = DriverManager.getConnection(
				"jdbc:sqlite:" + workingState.toUri().toASCIIString() + "?mode=ro&busy_timeout=500")) {
				try (PreparedStatement statement = database.prepareStatement(
					"SELECT x,y,online FROM players WHERE id=?")) {
					statement.setInt(1, accountId);
					try (ResultSet row = statement.executeQuery()) {
						if (!row.next() || row.getInt(1) != x || row.getInt(2) != y || row.getInt(3) != 0)
							throw new IOException("disposable player position/logout did not persist");
					}
				}
				requireRow(database, "SELECT prayer,magic,woodcut FROM curstats WHERE playerID=?",
					accountId, prayer, magic, woodcut);
				requireRow(database, "SELECT s.amount FROM invitems i JOIN itemstatuses s "
					+ "ON s.itemID=i.itemID WHERE i.playerID=? AND s.catalogID=10",
					accountId, coins);
				requireRow(database, "SELECT stage FROM quests WHERE playerID=? AND id=1",
					accountId, questStage);
				try (PreparedStatement statement = database.prepareStatement(
					"SELECT value FROM player_cache WHERE playerID=? AND `key`=?")) {
					statement.setInt(1, accountId); statement.setString(2, "current_base_verifier");
					try (ResultSet row = statement.executeQuery()) {
						if (!row.next() || !Integer.toString(coins).equals(row.getString(1)))
							throw new IOException("disposable cache state did not persist");
					}
				}
			}
		}

		private JSONObject evidence(String serverAfter, String clientAfter,
			String inputsAfter, String workingSeeded, String workingFinal,
			int serverPort, int websocketPort) throws Exception {
			JSONObject composition = new JSONObject();
			for (String key : IDENTITY_FIELDS) composition.put(key, identity.getString(key));
			composition.put("identitySha256", sha256(regular(options, "composition-identity")));
			JSONObject source = new JSONObject();
			source.put("serverTreeBeforeSha256", sourceServerBefore);
			source.put("serverTreeAfterSha256", serverAfter);
			source.put("clientTreeBeforeSha256", sourceClientBefore);
			source.put("clientTreeAfterSha256", clientAfter);
			source.put("inputSetBeforeSha256", inputsBefore);
			source.put("inputSetAfterSha256", inputsAfter); source.put("unchanged", true);
			JSONObject execution = new JSONObject(); execution.put("endpoint", "127.0.0.1");
			execution.put("serverPort", serverPort); execution.put("websocketPort", websocketPort);
			execution.put("launchCount", 2); execution.put("mapPackageFingerprint", mapFingerprint);
			execution.put("disposableAccountId", accountId);
			execution.put("disposableUsernameSha256", sha256(username.getBytes(StandardCharsets.UTF_8)));
			execution.put("workingStateSeededSha256", workingSeeded);
			execution.put("workingStateFinalSha256", workingFinal);
			execution.put("disposableStateChanged", true);
			execution.put("stateOutsideRuntimeRoots", true);
			execution.put("persistenceVerified", true); execution.put("credentialDeleted", true);
			JSONObject evidence = new JSONObject();
			evidence.put("schemaId", "current-base-installed-execution-evidence-v1");
			evidence.put("manifestType", "current-base-installed-execution-evidence");
			evidence.put("verifierId", "current-base-installed-execution-v1");
			evidence.put("verifierContractSha256", contract.sha256);
			evidence.put("status", "verified"); evidence.put("composition", composition);
			evidence.put("source", source); evidence.put("execution", execution);
			evidence.put("runs", runs); evidence.put("logs", logs); return evidence;
		}

		private void writeCredential() throws Exception {
			JSONObject value = new JSONObject(); value.put("username", username); value.put("password", password);
			Files.createDirectories(credential.getParent());
			try {
				Set<PosixFilePermission> mode = PosixFilePermissions.fromString("rw-------");
				Files.createFile(credential, PosixFilePermissions.asFileAttribute(mode));
			} catch (UnsupportedOperationException unsupported) { Files.createFile(credential); }
			Files.write(credential, (value.toString() + "\n").getBytes(StandardCharsets.UTF_8),
				StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
		}

		private String uniqueUsername(Connection database) throws Exception {
			for (int attempt = 0; attempt < 100; attempt++) {
				String value = "verify" + randomText(6, "abcdefghjkmnpqrstuvwxyz23456789");
				try (PreparedStatement statement = database.prepareStatement(
					"SELECT COUNT(*) FROM players WHERE LOWER(username)=LOWER(?)")) {
					statement.setString(1, value);
					try (ResultSet result = statement.executeQuery()) {
						if (result.next() && result.getInt(1) == 0) return value;
					}
				}
			}
			throw new IOException("could not allocate a disposable account name");
		}
	}

	private static final class Contract {
		private final String sha256;
		private Contract(String sha256) { this.sha256 = sha256; }
		private static Contract load(Path path) throws Exception {
			if (Files.size(path) > 1048576) throw new IOException("verifier contract exceeds one MiB");
			byte[] bytes = Files.readAllBytes(path); JSONObject value = new JSONObject(
				new String(bytes, StandardCharsets.UTF_8));
			requireKeys(value, set("schemaId", "manifestType", "verifierId", "invocation",
				"executionPolicy", "isolationPolicy", "requiredObservations", "evidenceContract",
				"exitSemantics"), "verifier contract");
			if (!"current-base-installed-execution-v1".equals(value.getString("schemaId"))
				|| !"current-base-installed-execution-verifier".equals(value.getString("manifestType"))
				|| !"current-base-installed-execution-v1".equals(value.getString("verifierId")))
				throw new IOException("verifier contract identity is unsupported");
			JSONObject invocation = value.getJSONObject("invocation");
			if (!"server-runtime".equals(invocation.getString("toolArtifactRole"))
				|| !CurrentBaseInstalledExecutionVerifier.class.getName().equals(
					invocation.getString("mainClass"))) throw new IOException(
				"verifier invocation is unsupported");
			JSONObject policy = value.getJSONObject("executionPolicy");
			if (!"sqlite".equals(policy.getString("engine"))
				|| !"127.0.0.1".equals(policy.getString("endpoint"))
				|| policy.getInt("launchCount") != 2
				|| policy.getInt("maximumLogBytesPerProcess") != MAX_LOG_BYTES
				|| policy.getInt("maximumMapManifestBytes") != MAX_MAP_MANIFEST_BYTES
				|| policy.getInt("maximumSourceFilesPerRoot") != MAX_SOURCE_FILES
				|| policy.getLong("maximumSourceBytesPerRoot") != MAX_SOURCE_BYTES)
				throw new IOException("verifier policy differs from compiled limits");
			if (!"java-awt-non-headless".equals(
				policy.getString("graphicalClientPrerequisite"))) throw new IOException(
				"verifier graphical prerequisite differs from compiled runtime");
			if (!"global-level-zero-sector-center-coverage-only".equals(
				policy.getString("mapSpawnSelection"))) throw new IOException(
				"verifier map spawn policy differs from compiled runtime");
			String actual = sha256(bytes);
			if (!CONTRACT_SHA256.equals(actual)) throw new IOException(
				"verifier contract does not match the compiled reviewed contract");
			return new Contract(actual);
		}
	}

	private static final class BoundedProcess {
		private final Process process; private final Path logPath;
		private final ByteArrayOutputStream output = new ByteArrayOutputStream();
		private final Thread reader; private volatile boolean truncated;
		private boolean closed, written;
		private BoundedProcess(Process process, Path logPath) {
			this.process = process; this.logPath = logPath;
			this.reader = new Thread(new Runnable() { public void run() { drain(); } },
				"current-base-verifier-output"); this.reader.setDaemon(true); this.reader.start();
		}
		private static BoundedProcess start(List<String> command, Path root, Path log)
			throws IOException {
			Files.createDirectories(log.getParent());
			ProcessBuilder builder = new ProcessBuilder(command); builder.directory(root.toFile());
			builder.redirectErrorStream(true); return new BoundedProcess(builder.start(), log);
		}
		private void drain() {
			byte[] buffer = new byte[8192];
			try (InputStream input = process.getInputStream()) { int count;
				while ((count = input.read(buffer)) >= 0) if (count > 0) synchronized (output) {
					int available = MAX_LOG_BYTES - output.size();
					if (available > 0) output.write(buffer, 0, Math.min(available, count));
					if (count > available) truncated = true;
				}
			} catch (IOException ignored) { }
		}
		private String text() { synchronized (output) {
			return new String(output.toByteArray(), StandardCharsets.UTF_8); } }
		private String awaitText(String needle, int seconds, String label) throws Exception {
			long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(seconds);
			while (System.nanoTime() < deadline) {
				String value = text(); if (value.contains(needle)) return value;
				if (!process.isAlive()) throw new IOException(label + " exited early with "
					+ process.exitValue() + "; inspect bounded workspace logs");
				Thread.sleep(200);
			}
			throw new IOException("timed out waiting for " + label
				+ "; inspect bounded workspace logs");
		}
		private boolean waitFor(int seconds) throws InterruptedException {
			return process.waitFor(seconds, TimeUnit.SECONDS);
		}
		private int exitValue() { return process.exitValue(); }
		private void close() throws Exception {
			if (!closed) {
				if (process.isAlive()) { process.destroy(); if (!process.waitFor(20, TimeUnit.SECONDS)) {
					process.destroyForcibly(); process.waitFor(10, TimeUnit.SECONDS);
					if (process.isAlive()) throw new IOException(
						"child process could not be forcibly terminated"); } }
				reader.join(5000); closed = true;
			}
			writeLog();
		}
		private void closeQuietly() { try { close(); } catch (Exception ignored) {
			if (process.isAlive()) { process.destroyForcibly(); try {
				process.waitFor(10, TimeUnit.SECONDS); } catch (InterruptedException interrupted) {
				Thread.currentThread().interrupt(); } }
		} }
		private void writeLog() throws Exception {
			if (written) return; byte[] value;
			synchronized (output) { value = output.toByteArray(); }
			Files.write(logPath, value, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
			written = true;
		}
		private JSONObject logRecord(int run, String role) throws Exception {
			writeLog(); JSONObject row = new JSONObject(); row.put("run", run); row.put("role", role);
			row.put("sha256", sha256(logPath)); row.put("size", Files.size(logPath));
			row.put("truncated", truncated); return row;
		}
	}

	private static void validateIdentity(JSONObject value) throws IOException {
		if (!"current-composition-identity-v1".equals(value.optString("schemaId"))
			|| !"current-platform-composition-identity".equals(value.optString("manifestType"))
			|| !"rsc-current-platform-r1".equals(value.optString("platformReleaseId"))
			|| !"current-base-v1".equals(value.optString("variantId"))
			|| !value.optBoolean("installable", false)) throw new IOException(
			"composition identity is not installable Current Base");
		for (String field : IDENTITY_FIELDS) if (field.endsWith("Hash")
			&& !HASH.matcher(value.optString(field)).matches()) throw new IOException(
			"composition identity field is invalid: " + field);
	}

	private static void requireInventoryHash(JSONObject identity, String role, Path path)
		throws Exception {
		if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path))
			throw new IOException("installed artifact for role " + role + " is missing or unsafe");
		JSONArray inventory = identity.getJSONArray("bundleInventory");
		String expected = null;
		for (int index = 0; index < inventory.length(); index++) {
			JSONObject row = inventory.getJSONObject(index);
			if (!role.equals(row.optString("role"))) continue;
			if (expected != null) throw new IOException("composition repeats artifact role " + role);
			expected = row.getString("sha256");
		}
		if (expected == null || !HASH.matcher(expected).matches()
			|| !expected.equals(sha256(path))) throw new IOException(
			"installed artifact hash differs for role " + role);
	}

	private static void validateRuntimeProfile(JSONObject profile, Path configPath)
		throws Exception {
		if (!"current-base-runtime-profile-v1".equals(profile.optString("schemaId"))
			|| !"current-base-v1".equals(profile.optString("variantId"))) throw new IOException(
			"runtime profile is not Current Base");
		Map<String,String> config = config(configPath);
		JSONObject excluded = profile.getJSONObject("advancedExclusions")
			.getJSONObject("configuration");
		for (String key : excluded.keySet()) if (excluded.getBoolean(key)
			|| !"false".equals(config.get(key))) throw new IOException(
			"server config does not exclude Advanced setting: " + key);
	}

	private static void renderVerificationConfig(Path path, int serverPort,
		int websocketPort) throws IOException {
		List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
		Map<String,String> replacements = new LinkedHashMap<String,String>();
		replacements.put("db_name", "current_base");
		replacements.put("server_bind_address", "127.0.0.1");
		replacements.put("server_port", Integer.toString(serverPort));
		replacements.put("ws_server_port", Integer.toString(websocketPort));
		Set<String> found = new LinkedHashSet<String>();
		for (int index = 0; index < lines.size(); index++) {
			String original = lines.get(index);
			String content = original.split("#", 2)[0];
			int separator = content.indexOf(':'); if (separator < 1) continue;
			String key = content.substring(0, separator).trim();
			if (!replacements.containsKey(key)) continue;
			if (!found.add(key)) throw new IOException("server config repeats verification key: " + key);
			int start = 0; while (start < original.length() && Character.isWhitespace(original.charAt(start))) start++;
			lines.set(index, original.substring(0, start) + key + ": " + replacements.get(key));
		}
		if (!found.equals(replacements.keySet())) throw new IOException(
			"server config lacks a required verification override");
		Files.write(path, (String.join("\n", lines) + "\n").getBytes(StandardCharsets.UTF_8),
			StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
	}

	private static void writeVerificationConnections(Path path) throws IOException {
		Files.deleteIfExists(path);
		Files.write(path, ("db_type: sqlite\n\ndatabase:\n\tdb_name: current_base\n")
			.getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE_NEW,
			StandardOpenOption.WRITE);
	}

	private static String installedPackageRelative(JSONObject value, String role)
		throws IOException {
		if (!value.optBoolean("active", false)
			|| !value.optString("manifestType").equals(
				"world-builder-installed-" + role + "-profile")) throw new IOException(
			role + " installed profile is inactive or unsupported");
		if (!HASH.matcher(value.optString("packageFingerprintSha256")).matches())
			throw new IOException(role + " installed profile package hash is invalid");
		return value.getString("packageRelativePath");
	}

	private static int[] mapCoordinate(Path map) throws Exception {
		JSONObject manifest = object(map.resolve("manifest.json"), "map manifest",
			MAX_MAP_MANIFEST_BYTES);
		JSONArray sectors = manifest.getJSONArray("terrainSectors");
		if (sectors.length() == 0) throw new IOException("canonical map has no terrain sectors");
		JSONObject sector = null;
		for (int index = 0; index < sectors.length(); index++) {
			JSONObject candidate = sectors.getJSONObject(index);
			if (!"global".equals(candidate.optString("worldSpace"))
				|| candidate.optInt("level", -1) != 0) continue;
			sector = candidate;
			if (candidate.getInt("sectorX") == 2 && candidate.getInt("sectorY") == 13) break;
		}
		if (sector == null) throw new IOException(
			"canonical map lacks a supported global level-zero spawn sector");
		return new int[] { sector.getInt("sectorX") * 48 + 24,
			sector.getInt("sectorY") * 48 + 24 };
	}

	private static Map<String,String> config(Path path) throws IOException {
		Map<String,String> values = new LinkedHashMap<String,String>();
		for (String raw : Files.readAllLines(path, StandardCharsets.UTF_8)) {
			String line = raw.split("#", 2)[0].trim(); int separator = line.indexOf(':');
			if (separator < 1) continue; String key = line.substring(0, separator).trim();
			String value = line.substring(separator + 1).trim();
			if (values.put(key, value) != null) throw new IOException(
				"server config repeats key: " + key);
		}
		return values;
	}

	private static void requireGraphicalEnvironment() throws IOException {
		if (GraphicsEnvironment.isHeadless()) throw new IOException(
			"installed execution requires a non-headless graphical Java environment");
	}

	private static void requireDisjoint(Path output, String label, Path... inputs)
		throws IOException {
		for (Path input : inputs) if (output.equals(input)
			|| output.startsWith(input) || input.startsWith(output)) throw new IOException(
			label + " must be disjoint from every supplied input");
	}

	private static void createPrivateDirectory(Path path) throws IOException {
		try {
			Files.createDirectory(path, PosixFilePermissions.asFileAttribute(
				PosixFilePermissions.fromString("rwx------")));
		} catch (UnsupportedOperationException unsupported) {
			Files.createDirectory(path);
		}
	}

	private static void setOwnerOnly(Path path, boolean executable) throws IOException {
		try {
			Files.setPosixFilePermissions(path, PosixFilePermissions.fromString(
				executable ? "rwx------" : "rw-------"));
		} catch (UnsupportedOperationException ignored) { }
	}

	private static String inputSetHash(Path... paths) throws Exception {
		MessageDigest digest = digest(); int index = 0;
		for (Path path : paths) { update(digest, Integer.toString(index++) + "\0");
			update(digest, Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
				? treeHash(path) : sha256(path)); update(digest, "\0"); }
		return hex(digest.digest());
	}

	private static void requireNoSqliteSidecars(Path database) throws IOException {
		for (String suffix : Arrays.asList("-wal", "-shm", "-journal")) {
			Path sidecar = database.resolveSibling(database.getFileName().toString() + suffix);
			if (Files.exists(sidecar, LinkOption.NOFOLLOW_LINKS)) throw new IOException(
				"state database has an active or residual SQLite sidecar");
		}
	}

	private static String treeHash(Path root) throws Exception {
		final List<Path> files = new ArrayList<Path>(); final long[] bytes = {0};
		Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
			@Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs)
				throws IOException {
				if (Files.isSymbolicLink(dir)) throw new IOException("source tree contains a symbolic link");
				return FileVisitResult.CONTINUE;
			}
			@Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
				throws IOException {
				if (!attrs.isRegularFile() || Files.isSymbolicLink(file)) throw new IOException(
					"source tree contains a non-regular file");
				files.add(file); bytes[0] += attrs.size();
				if (files.size() > MAX_SOURCE_FILES || bytes[0] > MAX_SOURCE_BYTES)
					throw new IOException("source tree exceeds reviewed verifier limits");
				return FileVisitResult.CONTINUE;
			}
		});
		Collections.sort(files, new Comparator<Path>() { public int compare(Path a, Path b) {
			return root.relativize(a).toString().compareTo(root.relativize(b).toString()); } });
		MessageDigest digest = digest();
		for (Path file : files) { update(digest, root.relativize(file).toString().replace('\\','/'));
			update(digest, "\0"); update(digest, sha256(file)); update(digest, "\0"); }
		return hex(digest.digest());
	}

	private static void copyTree(final Path source, final Path target) throws IOException {
		Files.walkFileTree(source, new SimpleFileVisitor<Path>() {
			@Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs)
				throws IOException { if (Files.isSymbolicLink(dir)) throw new IOException(
					"cannot copy symbolic-link directory"); Files.createDirectories(
					target.resolve(source.relativize(dir))); return FileVisitResult.CONTINUE; }
			@Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
				throws IOException { if (!attrs.isRegularFile() || Files.isSymbolicLink(file))
					throw new IOException("cannot copy non-regular source file"); copyFile(file,
						target.resolve(source.relativize(file))); return FileVisitResult.CONTINUE; }
		});
	}

	private static void replaceTree(Path source, Path target) throws IOException {
		deleteTree(target); copyTree(source, target);
	}

	private static void deleteTree(Path root) throws IOException {
		if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS)) return;
		Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
			@Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
				throws IOException { Files.delete(file); return FileVisitResult.CONTINUE; }
			@Override public FileVisitResult postVisitDirectory(Path dir, IOException failure)
				throws IOException { if (failure != null) throw failure; Files.delete(dir);
					return FileVisitResult.CONTINUE; }
		});
	}

	private static void copyFile(Path source, Path target) throws IOException {
		Files.createDirectories(target.getParent()); Files.copy(source, target,
			StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.COPY_ATTRIBUTES);
	}

	private static Path safeRelative(String value) throws IOException {
		Path relative = Paths.get(value).normalize();
		if (relative.isAbsolute() || relative.getNameCount() == 0
			|| relative.startsWith("..") || value.indexOf('\\') >= 0) throw new IOException(
			"installed package relative path is unsafe");
		return relative;
	}

	private static int scalar(Connection connection, String sql) throws Exception {
		try (Statement statement = connection.createStatement(); ResultSet result =
			statement.executeQuery(sql)) { if (!result.next()) throw new IOException(
			"database scalar query returned no row"); return result.getInt(1); }
	}

	private static void update(Connection connection, String sql, int first, int second)
		throws Exception { try (PreparedStatement statement = connection.prepareStatement(sql)) {
		statement.setInt(1, first); statement.setInt(2, second); statement.executeUpdate(); } }

	private static void requireRow(Connection connection, String sql, int playerId,
		int... expected) throws Exception {
		try (PreparedStatement statement = connection.prepareStatement(sql)) {
			statement.setInt(1, playerId);
			try (ResultSet row = statement.executeQuery()) {
				if (!row.next()) throw new IOException("disposable durable state row is missing");
				for (int index = 0; index < expected.length; index++)
					if (row.getInt(index + 1) != expected[index]) throw new IOException(
						"disposable durable state row differs after restart");
			}
		}
	}

	private static int integer(String value) throws IOException {
		try { return Integer.parseInt(value); } catch (NumberFormatException failure) {
			throw new IOException("runtime evidence contains a non-integer"); }
	}

	private static int port(Map<String,String> options, String key) throws IOException {
		int value = integer(required(options, key)); if (value < 1 || value > 65535)
			throw new IOException("--" + key + " is outside the valid port range"); return value;
	}

	private static String randomText(int length, String alphabet) {
		StringBuilder value = new StringBuilder(length);
		for (int index = 0; index < length; index++) value.append(
			alphabet.charAt(RANDOM.nextInt(alphabet.length()))); return value.toString();
	}

	private static String javaCommand() {
		return Paths.get(System.getProperty("java.home"), "bin", "java").toString();
	}

	private static JSONObject object(Path path, String label) throws IOException {
		return object(path, label, 1048576);
	}

	private static JSONObject object(Path path, String label, int maximumBytes)
		throws IOException {
		if (Files.size(path) > maximumBytes) throw new IOException(label + " exceeds its reviewed size limit");
		try { return new JSONObject(new String(Files.readAllBytes(path), StandardCharsets.UTF_8)); }
		catch (RuntimeException failure) { throw new IOException(label + " is invalid JSON"); }
	}

	private static Map<String,String> options(String[] arguments) {
		Map<String,String> result = new LinkedHashMap<String,String>();
		for (int index = 0; index < arguments.length; index++) {
			String raw = arguments[index]; if (!raw.startsWith("--") || ++index >= arguments.length)
				throw new IllegalArgumentException("invalid installed-execution argument");
			String key = raw.substring(2); if (result.put(key, arguments[index]) != null)
				throw new IllegalArgumentException("duplicate --" + key);
		}
		return result;
	}

	private static String required(Map<String,String> options, String key) {
		String value = options.get(key); if (value == null || value.trim().isEmpty())
			throw new IllegalArgumentException("--" + key + " is required"); return value.trim();
	}

	private static Path regular(Map<String,String> options, String key) throws IOException {
		Path path = Paths.get(required(options,key)).toAbsolutePath().normalize();
		if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path))
			throw new IOException("--" + key + " is not a regular non-link file");
		return path.toRealPath();
	}

	private static Path directory(Map<String,String> options, String key) throws IOException {
		Path path = Paths.get(required(options,key)).toAbsolutePath().normalize();
		if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path))
			throw new IOException("--" + key + " is not a directory non-link");
		return path.toRealPath();
	}

	private static Path newDirectory(Map<String,String> options, String key) throws IOException {
		Path path = Paths.get(required(options,key)).toAbsolutePath().normalize();
		if (Files.exists(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path))
			throw new IOException("--" + key + " must not already exist");
		if (path.getParent() == null || !Files.isDirectory(path.getParent()))
			throw new IOException("--" + key + " parent must exist");
		Path parent = path.getParent().toRealPath();
		return parent.resolve(path.getFileName()).normalize();
	}

	private static Path newOutput(Map<String,String> options, String key) throws IOException {
		Path path = Paths.get(required(options,key)).toAbsolutePath().normalize();
		if (Files.exists(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path))
			throw new IOException("--" + key + " must not already exist");
		if (path.getParent() == null || !Files.isDirectory(path.getParent())) throw new IOException(
			"--" + key + " parent must exist");
		return path.getParent().toRealPath().resolve(path.getFileName()).normalize();
	}

	private static void requireKeys(JSONObject value, Set<String> expected, String label)
		throws IOException { if (!value.keySet().equals(expected)) throw new IOException(
		label + " keys differ from the closed contract"); }

	private static Set<String> set(String... values) { return Collections.unmodifiableSet(
		new LinkedHashSet<String>(Arrays.asList(values))); }
	private static MessageDigest digest() throws Exception { return MessageDigest.getInstance("SHA-256"); }
	private static void update(MessageDigest digest, String value) { digest.update(value.getBytes(StandardCharsets.UTF_8)); }
	private static String sha256(Path path) throws Exception { MessageDigest digest = digest(); byte[] buffer = new byte[65536];
		try (InputStream input = Files.newInputStream(path)) { int count; while ((count = input.read(buffer)) >= 0)
			if (count > 0) digest.update(buffer, 0, count); } return hex(digest.digest()); }
	private static String sha256(byte[] value) throws Exception { return hex(digest().digest(value)); }
	private static String hex(byte[] value) { StringBuilder result = new StringBuilder();
		for (byte item : value) result.append(String.format("%02x", item & 255)); return result.toString(); }
	private static String safeMessage(Exception failure, Map<String,String> options) {
		String value = failure.getMessage();
		value = value == null ? failure.getClass().getSimpleName()
			: value.replaceAll("[\\r\\n]+", " ");
		if (options != null) for (Map.Entry<String,String> option : options.entrySet())
			if (!option.getKey().endsWith("port") && option.getValue() != null
				&& !option.getValue().isEmpty()) value = value.replace(option.getValue(), "<redacted-path>");
		return value;
	}
}

package com.openrsc.server.database;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** Offline, source-preserving migration into a staged Current Base database. */
public final class CurrentBaseStateMigration {
	private static final String ROW_ID = "preservation-retro-to-current-base-v1";
	private static final String CONTRACT_TYPE = "current-base-state-migration";
	private static final String CONTRACT_SHA256 =
		"06f2bca49f7e4dd653545695fd74ced91e9b306c9b7514bba114ea9361be2477";
	private static final Pattern NAME = Pattern.compile("[A-Za-z_][A-Za-z0-9_]*");
	private static final Pattern HASH = Pattern.compile("[0-9a-f]{64}");
	private static final Set<String> CONTRACT_KEYS = set(
		"schemaId", "manifestType", "migrationRowId", "targetStateContractId",
		"supportedEngines", "transformations", "invocation", "evidenceContract");
	private static final Set<String> ENGINE_KEYS = set(
		"engine", "sourceSchemaId", "sourceSchemaFingerprint",
		"sourceSchemaFingerprintAlgorithm", "verificationRuntime", "stageMode", "sourceMutation",
		"rollback", "credentialPolicy");
	private static final Set<String> TRANSFORM_KEYS = set(
		"tables", "legacyColumnsRetained", "columnMappings", "newColumnDefaults",
		"runtimePatchState");
	private static final Set<String> INVOCATION_KEYS = set(
		"toolArtifactRole", "mainClass", "arguments");
	private static final Set<String> EVIDENCE_KEYS = set(
		"schemaId", "requiredFields", "sourceStateComparison", "stageStateComparison");
	private static final Set<String> SQLITE_OPTIONS = set(
		"contract", "engine", "evidence", "source", "stage", "fail-after-copy");
	private static final Set<String> MARIA_OPTIONS = set(
		"contract", "engine", "evidence", "host", "port", "source-schema",
		"stage-schema", "user-env", "password-env", "fail-after-copy");

	private CurrentBaseStateMigration() { }

	public static void main(String[] arguments) {
		try {
			Map<String, String> options = options(arguments);
			String engine = required(options, "engine");
			requireOptionSet(options, "sqlite".equals(engine) ? SQLITE_OPTIONS
				: "mariadb".equals(engine) ? MARIA_OPTIONS : Collections.<String>emptySet());
			boolean injectedFailure = options.containsKey("fail-after-copy");
			if (injectedFailure && !Boolean.getBoolean(
				"openrsc.currentBaseMigrationTestFailure")) throw new IOException(
				"failure injection is disabled outside the sealed test harness");
			Path contractPath = regular(options, "contract");
			Path evidencePath = newOutputPath(options, "evidence");
			Contract contract = Contract.load(contractPath);
			if ("sqlite".equals(engine)) {
				migrateSqlite(contract, regular(options, "source"),
					newOutputPath(options, "stage"), evidencePath, injectedFailure);
			} else if ("mariadb".equals(engine)) {
				migrateMaria(contract, MariaTarget.load(options), evidencePath,
					injectedFailure);
			} else {
				throw new IllegalArgumentException("unsupported engine: " + engine);
			}
		} catch (Exception failure) {
			System.err.println("Current Base state migration refused: " + failure.getMessage());
			System.exit(2);
		}
	}

	private static void migrateSqlite(Contract contract, Path source, Path stage,
		Path evidence, boolean injectedFailure) throws Exception {
		contract.requireEngine("sqlite");
		if (source.equals(stage)) {
			throw new IOException("SQLite stage must be a new path distinct from source");
		}
		Files.createDirectories(stage.toAbsolutePath().normalize().getParent());
		String sourceBytes = sha256(source);
		boolean stageOwned = false;
		try (Connection sourceDb = DriverManager.getConnection(
			"jdbc:sqlite:file:" + source.toAbsolutePath() + "?mode=ro")) {
			Schema sourceSchema = sqliteSchema(sourceDb);
			contract.requireFingerprint("sqlite", sourceSchema.fingerprint);
			String sourceState = stateHash(sourceDb, sourceSchema, null);
			Files.createFile(stage);
			stageOwned = true;
			Files.copy(source, stage, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
			if (injectedFailure) throw new SQLException("injected failure after staged copy");
			try (Connection staged = DriverManager.getConnection(
				"jdbc:sqlite:" + stage.toAbsolutePath())) {
				staged.setAutoCommit(false);
				try {
					applyTransform(staged, "sqlite");
					String projected = stateHash(staged, sourceSchema, null);
					if (!sourceState.equals(projected)) throw new SQLException(
						"staged SQLite database did not preserve source durable rows");
					writeRuntimePatchLedger(staged, "sqlite");
					writeLedger(staged, contract, sourceSchema.fingerprint, sourceState);
					staged.commit();
					writeEvidence(evidence, contract, "sqlite", sourceSchema.fingerprint,
						sourceState, projected, sourceBytes, sha256(source), stage.toString());
				} catch (Exception failure) {
					staged.rollback();
					throw failure;
				}
			}
		} catch (Exception failure) {
			if (stageOwned) try { Files.deleteIfExists(stage); } catch (IOException ignored) { }
			throw failure;
		}
	}

	private static void migrateMaria(Contract contract, MariaTarget target,
		Path evidence, boolean injectedFailure) throws Exception {
		contract.requireEngine("mariadb");
		boolean stageOwned = false;
		try (Connection connection = target.connect()) {
			if (schemaExists(connection, target.stageSchema)) throw new SQLException(
				"MariaDB stage schema already exists");
			Schema sourceSchema = mariaSchema(connection, target.sourceSchema);
			contract.requireFingerprint("mariadb", sourceSchema.fingerprint);
			String sourceState = stateHash(connection, sourceSchema, target.sourceSchema);
			try (Statement statement = connection.createStatement()) {
				statement.executeUpdate("CREATE DATABASE " + quote(target.stageSchema));
				stageOwned = true;
				for (Table table : sourceSchema.tables) {
					statement.executeUpdate("CREATE TABLE " + quote(target.stageSchema) + "."
						+ quote(table.name) + " LIKE " + quote(target.sourceSchema) + "."
						+ quote(table.name));
					statement.executeUpdate("INSERT INTO " + quote(target.stageSchema) + "."
						+ quote(table.name) + " SELECT * FROM " + quote(target.sourceSchema)
						+ "." + quote(table.name));
				}
			}
			if (injectedFailure) throw new SQLException("injected failure after staged copy");
			connection.setCatalog(target.stageSchema);
			applyTransform(connection, "mariadb");
			String projected = stateHash(connection, sourceSchema, target.stageSchema);
			if (!sourceState.equals(projected)) throw new SQLException(
				"staged MariaDB schema did not preserve source durable rows");
			writeRuntimePatchLedger(connection, "mariadb");
			writeLedger(connection, contract, sourceSchema.fingerprint, sourceState);
			writeEvidence(evidence, contract, "mariadb", sourceSchema.fingerprint,
				sourceState, projected, sourceState, sourceState, target.stageSchema);
		} catch (Exception failure) {
			if (stageOwned) target.dropOwnedStageQuietly();
			throw failure;
		}
	}

	private static void applyTransform(Connection connection, String engine)
		throws SQLException {
		for (String table : Arrays.asList("curstats", "maxstats", "experience",
			"capped_experience")) {
			boolean levels = "curstats".equals(table) || "maxstats".equals(table);
			int defaultValue = levels ? 1 : 0;
			addColumn(connection, engine, table, "prayer", defaultValue);
			addColumn(connection, engine, table, "magic", defaultValue);
			addColumn(connection, engine, table, "woodcut", defaultValue);
			for (String column : Arrays.asList("fletching", "fishing", "agility",
				"harvesting", "runecraft", "summoning", "blessing")) {
				addColumn(connection, engine, table, column, defaultValue);
			}
			try (Statement statement = connection.createStatement()) {
				statement.executeUpdate("UPDATE " + quote(table)
					+ " SET prayer=CASE WHEN praygood > prayevil THEN praygood ELSE prayevil END,"
					+ " magic=CASE WHEN goodmagic > evilmagic THEN goodmagic ELSE evilmagic END,"
					+ " woodcut=woodcutting");
			}
		}
		applyCurrentRuntimeSchema(connection, engine);
	}

	private static void applyCurrentRuntimeSchema(Connection connection, String engine)
		throws SQLException {
		try (Statement statement = connection.createStatement()) {
			if ("sqlite".equals(engine)) {
				statement.executeUpdate("CREATE TABLE former_names (dbid INTEGER NOT NULL "
					+ "PRIMARY KEY, playerId INTEGER NOT NULL, formerName VARCHAR(13) NOT NULL "
					+ "DEFAULT '0', changeType TINYINT NOT NULL DEFAULT 0, time INTEGER NOT NULL "
					+ "DEFAULT 0, whoChanged VARCHAR(12) NOT NULL DEFAULT '0', reason VARCHAR(120) "
					+ "NOT NULL DEFAULT '0')");
				statement.executeUpdate("ALTER TABLE players ADD COLUMN former_name "
					+ "VARCHAR(13) NOT NULL DEFAULT ''");
				statement.executeUpdate("ALTER TABLE friends ADD COLUMN friendFormerName "
					+ "VARCHAR(13) NOT NULL DEFAULT ''");
				statement.executeUpdate("ALTER TABLE ignores ADD COLUMN ignoreFormer "
					+ "BIGINT(19) NOT NULL DEFAULT 0");
				statement.executeUpdate("CREATE INDEX ignoreFormer ON ignores(ignoreFormer)");
				statement.executeUpdate("ALTER TABLE logins ADD COLUMN nonce VARCHAR(96)");
				statement.executeUpdate("CREATE UNIQUE INDEX nonce_index ON logins(nonce)");
			} else {
				statement.executeUpdate("CREATE TABLE former_names (dbid INT UNSIGNED NOT NULL "
					+ "AUTO_INCREMENT PRIMARY KEY, playerId INT UNSIGNED NULL, formerName "
					+ "VARCHAR(13) NOT NULL DEFAULT '0', changeType TINYINT UNSIGNED NOT NULL "
					+ "DEFAULT 0, time INT UNSIGNED NOT NULL DEFAULT 0, whoChanged VARCHAR(12) "
					+ "NOT NULL DEFAULT '0', reason VARCHAR(120) NOT NULL DEFAULT '0') "
					+ "DEFAULT CHARSET=utf8");
				statement.executeUpdate("ALTER TABLE players ADD COLUMN former_name "
					+ "VARCHAR(13) NOT NULL DEFAULT ''");
				statement.executeUpdate("ALTER TABLE friends ADD COLUMN friendFormerName "
					+ "VARCHAR(13) NOT NULL DEFAULT ''");
				statement.executeUpdate("ALTER TABLE ignores ADD COLUMN ignoreFormer "
					+ "BIGINT UNSIGNED NOT NULL DEFAULT 0, ADD INDEX ignoreFormer(ignoreFormer)");
				statement.executeUpdate("ALTER TABLE logins ADD COLUMN nonce VARCHAR(96) NULL, "
					+ "ADD UNIQUE INDEX nonce(nonce)");
			}
			statement.executeUpdate("CREATE TABLE IF NOT EXISTS db_patches (patch_name "
				+ "VARCHAR(200) NOT NULL PRIMARY KEY, run_date DATE NOT NULL)");
		}
	}

	private static void writeRuntimePatchLedger(Connection connection, String engine)
		throws SQLException {
		List<String> patches = "sqlite".equals(engine)
			? Arrays.asList("2021_05_11_add_db_patches.sql",
				"2023_02_01_former_names.sql", "2026_05_14_add_summoning_skill.sql",
				"2026_08_03_add_blessing_skill.sql")
			: Arrays.asList("2020_09_23_rsc235.sql", "2020_10_28_player_transfers.sql",
				"2021_03_14_xp_rollover.sql", "2021_03_24_message_logging_length.sql",
				"2021_05_11_add_db_patches.sql",
				"2021_05_27_move_ironman_to_separate_table.sql",
				"2021_05_28_delete_bank_size_from_players.sql",
				"2023_02_01_former_names.sql", "2023_12_23_change_itemid_to_bigint.sql",
				"2026_05_14_add_summoning_skill.sql",
				"2026_08_03_add_blessing_skill.sql");
		String insert = "sqlite".equals(engine)
			? "INSERT OR IGNORE INTO db_patches (patch_name,run_date) VALUES (?,?)"
			: "INSERT IGNORE INTO db_patches (patch_name,run_date) VALUES (?,?)";
		try (PreparedStatement statement = connection.prepareStatement(insert)) {
			for (String patch : patches) {
				statement.setString(1, patch);
				statement.setString(2, patch.substring(0, 10).replace('_', '-'));
				statement.addBatch();
			}
			statement.executeBatch();
		}
	}

	private static void addColumn(Connection connection, String engine, String table,
		String column, int defaultValue) throws SQLException {
		String type = "mariadb".equals(engine) ? "INT" : "INTEGER";
		try (Statement statement = connection.createStatement()) {
			statement.executeUpdate("ALTER TABLE " + quote(table) + " ADD COLUMN "
				+ quote(column) + " " + type + " NOT NULL DEFAULT " + defaultValue);
		}
	}

	private static void writeLedger(Connection connection, Contract contract,
		String sourceSchema, String sourceState) throws SQLException {
		try (Statement statement = connection.createStatement()) {
			statement.executeUpdate("CREATE TABLE current_base_migrations ("
				+ "migration_row_id VARCHAR(128) NOT NULL PRIMARY KEY,"
				+ "contract_sha256 CHAR(64) NOT NULL,"
				+ "source_schema_sha256 CHAR(64) NOT NULL,"
				+ "source_state_sha256 CHAR(64) NOT NULL,"
				+ "completed_at VARCHAR(40) NOT NULL)");
		}
		try (PreparedStatement statement = connection.prepareStatement(
			"INSERT INTO current_base_migrations VALUES (?,?,?,?,?)")) {
			statement.setString(1, ROW_ID);
			statement.setString(2, contract.sha256);
			statement.setString(3, sourceSchema);
			statement.setString(4, sourceState);
			statement.setString(5, Instant.now().toString());
			statement.executeUpdate();
		}
	}

	private static Schema sqliteSchema(Connection connection) throws Exception {
		List<Table> tables = new ArrayList<Table>();
		List<String> structures = new ArrayList<String>();
		try (Statement statement = connection.createStatement(); ResultSet result =
			statement.executeQuery("SELECT type,name FROM sqlite_master WHERE type IN "
				+ "('view','trigger') ORDER BY type,name")) {
			if (result.next()) throw new SQLException("SQLite views/triggers are unsupported: "
				+ result.getString(1) + ":" + result.getString(2));
		}
		try (Statement statement = connection.createStatement(); ResultSet result =
			statement.executeQuery("SELECT name FROM sqlite_master WHERE type='table' "
				+ "AND name NOT LIKE 'sqlite_%' ORDER BY name")) {
			while (result.next()) {
				String table = result.getString(1);
				List<String> columns = new ArrayList<String>();
				try (Statement columnsStatement = connection.createStatement();
					ResultSet columnResult = columnsStatement.executeQuery(
						"PRAGMA table_info(" + quote(table) + ")")) {
					while (columnResult.next()) columns.add(columnResult.getString("name")
						+ ":" + normalizeType(columnResult.getString("type"))
						+ ":" + columnResult.getInt("notnull")
						+ ":" + nullableText(columnResult.getString("dflt_value"))
						+ ":" + columnResult.getInt("pk"));
				}
				tables.add(new Table(table, columns));
			}
		}
		try (Statement statement = connection.createStatement(); ResultSet result =
			statement.executeQuery("SELECT tbl_name,name,sql FROM sqlite_master "
				+ "WHERE type='index' AND sql IS NOT NULL ORDER BY tbl_name,name")) {
			while (result.next()) structures.add("index:" + result.getString(1) + ":"
				+ result.getString(2) + ":" + normalizeSql(result.getString(3)));
		}
		return new Schema(tables, structures);
	}

	private static Schema mariaSchema(Connection connection, String catalog)
		throws Exception {
		List<Table> tables = new ArrayList<Table>();
		List<String> structures = new ArrayList<String>();
		try (PreparedStatement statement = connection.prepareStatement(
			"SELECT TABLE_NAME,TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES "
				+ "WHERE TABLE_SCHEMA=? AND TABLE_TYPE<>'BASE TABLE' ORDER BY TABLE_NAME")) {
			statement.setString(1, catalog);
			try (ResultSet result = statement.executeQuery()) {
				if (result.next()) throw new SQLException("MariaDB non-table object is unsupported: "
					+ result.getString(1) + ":" + result.getString(2));
			}
		}
		for (String query : Arrays.asList(
			"SELECT TRIGGER_NAME FROM INFORMATION_SCHEMA.TRIGGERS WHERE TRIGGER_SCHEMA=?",
			"SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES WHERE ROUTINE_SCHEMA=?")) {
			try (PreparedStatement statement = connection.prepareStatement(query)) {
				statement.setString(1, catalog);
				try (ResultSet result = statement.executeQuery()) {
					if (result.next()) throw new SQLException(
						"MariaDB triggers/routines are unsupported: " + result.getString(1));
				}
			}
		}
		try (PreparedStatement statement = connection.prepareStatement(
			"SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,"
				+ "COLUMN_KEY,EXTRA,GENERATION_EXPRESSION,CHARACTER_SET_NAME,COLLATION_NAME FROM "
				+ "INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? "
				+ "ORDER BY TABLE_NAME,ORDINAL_POSITION")) {
			statement.setString(1, catalog);
			try (ResultSet result = statement.executeQuery()) {
				Table current = null;
				while (result.next()) {
					String name = result.getString(1);
					if (current == null || !current.name.equals(name)) {
						current = new Table(name, new ArrayList<String>());
						tables.add(current);
					}
					current.columns.add(result.getString(2) + ":"
						+ normalizeType(result.getString(3)) + ":"
						+ ("NO".equals(result.getString(4)) ? "1" : "0") + ":"
						+ nullableText(result.getString(5)) + ":"
						+ nullableText(result.getString(6)) + ":"
						+ nullableText(result.getString(7)) + ":"
						+ nullableText(result.getString(8)) + ":"
						+ nullableText(result.getString(9)) + ":"
						+ nullableText(result.getString(10)));
				}
			}
		}
		if (tables.isEmpty()) throw new SQLException("MariaDB source schema is missing");
		try (PreparedStatement statement = connection.prepareStatement(
			"SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,COLLATION,"
				+ "SUB_PART,INDEX_TYPE FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA=? "
				+ "ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX")) {
			statement.setString(1, catalog);
			try (ResultSet result = statement.executeQuery()) {
				while (result.next()) structures.add("index:" + result.getString(1) + ":"
					+ result.getString(2) + ":" + result.getInt(3) + ":"
					+ result.getInt(4) + ":" + nullableText(result.getString(5)) + ":"
					+ nullableText(result.getString(6)) + ":" + nullableText(result.getString(7))
					+ ":" + nullableText(result.getString(8)));
			}
		}
		return new Schema(tables, structures);
	}

	private static String stateHash(Connection connection, Schema schema, String catalog)
		throws Exception {
		MessageDigest digest = MessageDigest.getInstance("SHA-256");
		for (Table table : schema.tables) {
			List<String> rows = new ArrayList<String>();
			String qualified = catalog == null ? quote(table.name)
				: quote(catalog) + "." + quote(table.name);
			try (Statement statement = connection.createStatement(); ResultSet result =
				statement.executeQuery("SELECT * FROM " + qualified)) {
				ResultSetMetaData metadata = result.getMetaData();
				int count = table.columns.size();
				while (result.next()) {
					StringBuilder row = new StringBuilder();
					for (int index = 1; index <= count; index++) {
						byte[] bytes = result.getBytes(index);
						row.append(index).append('=');
						if (bytes == null) row.append("null");
						else row.append(hex(bytes));
						row.append(';');
					}
					rows.add(row.toString());
				}
			}
			Collections.sort(rows);
			update(digest, table.name + "\n");
			for (String row : rows) update(digest, row + "\n");
		}
		return hex(digest.digest());
	}

	private static boolean schemaExists(Connection connection, String schema)
		throws SQLException {
		try (PreparedStatement statement = connection.prepareStatement(
			"SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME=?")) {
			statement.setString(1, schema);
			try (ResultSet result = statement.executeQuery()) {
				return result.next() && result.getInt(1) != 0;
			}
		}
	}

	private static void writeEvidence(Path path, Contract contract, String engine,
		String sourceSchema, String sourceState, String stagedProjection,
		String sourceBefore, String sourceAfter, String stageLocation) throws Exception {
		JSONObject evidence = new JSONObject();
		evidence.put("schemaId", "current-base-state-migration-evidence-v1");
		evidence.put("manifestType", "current-base-state-migration-evidence");
		evidence.put("migrationRowId", ROW_ID);
		evidence.put("engine", engine);
		evidence.put("contractSha256", contract.sha256);
		evidence.put("sourceSchemaFingerprint", sourceSchema);
		evidence.put("sourceStateSha256", sourceState);
		evidence.put("stagedSourceProjectionSha256", stagedProjection);
		evidence.put("sourceBeforeSha256", sourceBefore);
		evidence.put("sourceAfterSha256", sourceAfter);
		evidence.put("sourceUnchanged", sourceBefore.equals(sourceAfter));
		evidence.put("stageLocation", stageLocation);
		evidence.put("rollbackPolicy", "discard-stage-only");
		evidence.put("status", "verified");
		Files.createDirectories(path.toAbsolutePath().normalize().getParent());
		Files.write(path, (evidence.toString(2) + "\n").getBytes(StandardCharsets.UTF_8),
			java.nio.file.StandardOpenOption.CREATE_NEW,
			java.nio.file.StandardOpenOption.WRITE);
	}

	private static final class Contract {
		private final JSONObject document;
		private final String sha256;
		private Contract(JSONObject document, String sha256) {
			this.document = document; this.sha256 = sha256;
		}
		private static Contract load(Path path) throws Exception {
			if (Files.size(path) > 1024 * 1024) throw new IOException(
				"migration contract exceeds one MiB");
			byte[] bytes = Files.readAllBytes(path);
			JSONObject value = new JSONObject(new String(bytes, StandardCharsets.UTF_8));
			requireKeys(value, CONTRACT_KEYS, "migration contract");
			if (!"current-base-state-migration-v1".equals(value.getString("schemaId"))
				|| !CONTRACT_TYPE.equals(value.getString("manifestType"))
				|| !ROW_ID.equals(value.getString("migrationRowId"))
				|| !"canonical-public-state-v1".equals(value.getString("targetStateContractId"))) {
				throw new IOException("migration contract identity is unsupported");
			}
			JSONArray engines = value.getJSONArray("supportedEngines");
			if (engines.length() != 2) throw new IOException("migration engine matrix is incomplete");
			for (int index = 0; index < engines.length(); index++)
				requireKeys(engines.getJSONObject(index), ENGINE_KEYS, "engine row");
			requireKeys(value.getJSONObject("transformations"), TRANSFORM_KEYS,
				"transformations");
			requireKeys(value.getJSONObject("invocation"), INVOCATION_KEYS, "invocation");
			if (!"server-runtime".equals(value.getJSONObject("invocation")
				.getString("toolArtifactRole"))) throw new IOException(
				"migration tool artifact role is unsupported");
			requireKeys(value.getJSONObject("evidenceContract"), EVIDENCE_KEYS,
				"evidence contract");
			String actualHash = sha256(bytes);
			if (!CONTRACT_SHA256.equals(actualHash)) throw new IOException(
				"migration contract does not match the compiled reviewed row");
			return new Contract(value, actualHash);
		}
		private JSONObject requireEngine(String engine) throws IOException {
			JSONArray engines = document.getJSONArray("supportedEngines");
			for (int index = 0; index < engines.length(); index++) {
				JSONObject row = engines.getJSONObject(index);
				if (engine.equals(row.getString("engine"))) return row;
			}
			throw new IOException("migration engine is not contracted: " + engine);
		}
		private void requireFingerprint(String engine, String actual) throws IOException {
			String expected = requireEngine(engine).getString("sourceSchemaFingerprint");
			if (!HASH.matcher(expected).matches() || !expected.equals(actual)) throw new IOException(
				"unsupported or customized " + engine + " source schema: " + actual);
		}
	}

	private static final class MariaTarget {
		private final String host, sourceSchema, stageSchema, user, password;
		private final int port;
		private MariaTarget(String host, int port, String sourceSchema,
			String stageSchema, String user, String password) {
			this.host=host; this.port=port; this.sourceSchema=sourceSchema;
			this.stageSchema=stageSchema; this.user=user; this.password=password;
		}
		private static MariaTarget load(Map<String, String> options) throws Exception {
			String host = required(options, "host");
			if (!"127.0.0.1".equals(host)) throw new IOException(
				"MariaDB migration endpoint must be literal IPv4 loopback 127.0.0.1");
			int port = Integer.parseInt(required(options, "port"));
			if (port < 1 || port > 65535) throw new IOException("invalid MariaDB port");
			String source = safeName(required(options, "source-schema"));
			String stage = safeName(required(options, "stage-schema"));
			if (source.equals(stage)) throw new IOException("MariaDB stage must differ from source");
			String user = environment(options, "user-env");
			String password = environment(options, "password-env");
			return new MariaTarget(host, port, source, stage, user, password);
		}
		private Connection connect() throws SQLException {
			return DriverManager.getConnection("jdbc:mysql://" + host + ":" + port
				+ "/?useSSL=false&allowPublicKeyRetrieval=true", user, password);
		}
		private void dropOwnedStageQuietly() {
			try (Connection connection = connect(); Statement statement = connection.createStatement()) {
				statement.executeUpdate("DROP DATABASE IF EXISTS " + quote(stageSchema));
			} catch (Exception ignored) { }
		}
	}

	private static final class Schema {
		private final List<Table> tables;
		private final String fingerprint;
		private Schema(List<Table> tables, List<String> structures) throws Exception {
			this.tables = tables;
			MessageDigest digest = MessageDigest.getInstance("SHA-256");
			for (Table table : tables) {
				update(digest, table.name + "\n");
				for (String column : table.columns) update(digest, column + "\n");
			}
			for (String structure : structures) update(digest, structure + "\n");
			this.fingerprint = hex(digest.digest());
		}
	}
	private static final class Table {
		private final String name;
		private final List<String> columns;
		private Table(String name, List<String> columns) { this.name=name; this.columns=columns; }
	}

	private static Map<String,String> options(String[] arguments) {
		Map<String,String> result = new LinkedHashMap<String,String>();
		for (int index=0; index<arguments.length; index++) {
			String key=arguments[index];
			if (!key.startsWith("--")) throw new IllegalArgumentException("invalid argument: "+key);
			key=key.substring(2);
			if ("fail-after-copy".equals(key)) { result.put(key,"true"); continue; }
			if (++index>=arguments.length) throw new IllegalArgumentException("missing value for --"+key);
			if (result.put(key,arguments[index])!=null) throw new IllegalArgumentException("duplicate --"+key);
		}
		return result;
	}
	private static String required(Map<String,String> options,String key) {
		String value=options.get(key); if(value==null||value.trim().isEmpty())
			throw new IllegalArgumentException("--"+key+" is required"); return value.trim();
	}
	private static Path regular(Map<String,String> options,String key) throws IOException {
		Path path=Paths.get(required(options,key)).toAbsolutePath().normalize();
		if(!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)) throw new IOException("--"+key+" is not a regular file");
		return path;
	}
	private static Path outputPath(Map<String,String> options,String key) throws IOException {
		Path path=Paths.get(required(options,key)).toAbsolutePath().normalize();
		if(Files.isSymbolicLink(path)) throw new IOException("--"+key+" cannot be a symbolic link"); return path;
	}
	private static Path newOutputPath(Map<String,String> options,String key) throws IOException {
		Path path=outputPath(options,key);
		if(Files.exists(path,LinkOption.NOFOLLOW_LINKS)) throw new IOException("--"+key+" must not already exist");
		return path;
	}
	private static String environment(Map<String,String> options,String key) {
		String name=required(options,key); if(!NAME.matcher(name).matches()) throw new IllegalArgumentException("invalid environment name");
		String value=System.getenv(name); if(value==null) throw new IllegalArgumentException("missing credential environment: "+name); return value;
	}
	private static String safeName(String value) { if(!NAME.matcher(value).matches()) throw new IllegalArgumentException("unsafe schema name"); return value; }
	private static String quote(String value) { safeName(value); return "`"+value+"`"; }
	private static String normalizeType(String value) { return value==null?"":value.toLowerCase(Locale.ROOT).replaceAll("\\s+",""); }
	private static String normalizeSql(String value) { return value==null?"":value.trim().toLowerCase(Locale.ROOT).replaceAll("\\s+"," "); }
	private static String nullableText(String value) { return value==null?"<null>":value.trim().toLowerCase(Locale.ROOT); }
	private static void requireOptionSet(Map<String,String> options,Set<String> allowed) { if(allowed.isEmpty()||!allowed.containsAll(options.keySet())) throw new IllegalArgumentException("arguments differ from the closed engine invocation"); }
	private static void requireKeys(JSONObject object,Set<String> keys,String label) throws IOException { if(!object.keySet().equals(keys)) throw new IOException(label+" keys differ from closed contract"); }
	private static Set<String> set(String... values) { return Collections.unmodifiableSet(new LinkedHashSet<String>(Arrays.asList(values))); }
	private static void update(MessageDigest digest,String value) { digest.update(value.getBytes(StandardCharsets.UTF_8)); }
	private static String sha256(Path path) throws Exception { MessageDigest digest=MessageDigest.getInstance("SHA-256"); byte[] buffer=new byte[65536]; try(InputStream input=Files.newInputStream(path)){ int count; while((count=input.read(buffer))>=0){ if(count>0) digest.update(buffer,0,count); } } return hex(digest.digest()); }
	private static String sha256(byte[] bytes) throws Exception { MessageDigest digest=MessageDigest.getInstance("SHA-256"); return hex(digest.digest(bytes)); }
	private static String hex(byte[] bytes) { StringBuilder value=new StringBuilder(); for(byte item:bytes)value.append(String.format("%02x",item&255)); return value.toString(); }
}

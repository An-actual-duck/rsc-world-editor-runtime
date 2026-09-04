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
	private static final String CONTRACT_TYPE = "current-base-state-migration";
	private static final String CONTRACT_SHA256 =
		"30dadb10af095fa19ff39dd17d97bbf8bd69dc2888b41732ad5095b0841d7be5";
	private static final Pattern NAME = Pattern.compile("[A-Za-z_][A-Za-z0-9_]*");
	private static final Pattern HASH = Pattern.compile("[0-9a-f]{64}");
	private static final long MAXIMUM_SQLITE_SOURCE_BYTES = 4294967296L;
	private static final int MAXIMUM_ROWS_PER_TABLE = 1000000;
	private static final long MAXIMUM_ROW_DIGEST_BYTES_PER_TABLE = 67108864L;
	private static final long MAXIMUM_SOURCE_CELL_BYTES_PER_TABLE = 4294967296L;
	private static final Set<String> CONTRACT_KEYS = set(
		"schemaId", "manifestType", "migrationRows", "targetStateContractId",
		"supportedSources", "transformations", "resourceLimits", "invocation",
		"evidenceContract");
	private static final Set<String> ENGINE_KEYS = set(
		"migrationRowId", "engine", "sourceSchemaId", "sourceSchemaFingerprint",
		"sourceSchemaFingerprintAlgorithm", "verificationRuntime", "stageMode", "sourceMutation",
		"rollback", "credentialPolicy", "transformationId");
	private static final Set<String> TRANSFORM_KEYS = set(
		"profiles", "tables", "legacyColumnsRetained", "columnMappings", "newColumnDefaults",
		"runtimePatchState");
	private static final Set<String> INVOCATION_KEYS = set(
		"toolArtifactRole", "mainClass", "arguments");
	private static final Set<String> EVIDENCE_KEYS = set(
		"schemaId", "requiredFields", "sourceStateComparison", "stageStateComparison");
	private static final Set<String> RESOURCE_LIMIT_KEYS = set(
		"maximumSqliteSourceBytes", "maximumRowsPerTable",
		"maximumEncodedRowDigestBytesPerTable", "maximumSourceCellBytesPerTable");
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
		if (source.equals(stage)) {
			throw new IOException("SQLite stage must be a new path distinct from source");
		}
		if (Files.size(source) > MAXIMUM_SQLITE_SOURCE_BYTES) throw new IOException(
			"SQLite source exceeds the reviewed four-GiB migration limit");
		requireNoSqliteSidecars(source);
		Files.createDirectories(stage.toAbsolutePath().normalize().getParent());
		String sourceBytes = sha256(source);
		boolean stageOwned = false;
		try (Connection sourceDb = DriverManager.getConnection(
			"jdbc:sqlite:file:" + source.toAbsolutePath() + "?mode=ro")) {
			Schema sourceSchema = sqliteSchema(sourceDb);
			SourceRow sourceRow = contract.matchSource("sqlite", sourceSchema.fingerprint);
			String sourceState = stateHash(sourceDb, sourceSchema, null);
			Files.createFile(stage);
			stageOwned = true;
			Files.copy(source, stage, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
			if (injectedFailure) throw new SQLException("injected failure after staged copy");
			try (Connection staged = DriverManager.getConnection(
				"jdbc:sqlite:" + stage.toAbsolutePath())) {
				staged.setAutoCommit(false);
				try {
					applyTransform(staged, "sqlite", sourceRow.transformationId);
					String projected = stateHash(staged, sourceSchema, null);
					if (!sourceState.equals(projected)) throw new SQLException(
						"staged SQLite database did not preserve source durable rows");
					writeRuntimePatchLedger(staged, "sqlite");
					writeLedger(staged, contract, sourceRow, sourceSchema.fingerprint, sourceState);
					staged.commit();
					writeEvidence(evidence, contract, sourceRow, sourceSchema.fingerprint,
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
		boolean stageOwned = false;
		try (Connection connection = target.connect()) {
			if (schemaExists(connection, target.stageSchema)) throw new SQLException(
				"MariaDB stage schema already exists");
			Schema sourceSchema = mariaSchema(connection, target.sourceSchema);
			SourceRow sourceRow = contract.matchSource("mariadb", sourceSchema.fingerprint);
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
			applyTransform(connection, "mariadb", sourceRow.transformationId);
			String projected = stateHash(connection, sourceSchema, target.stageSchema);
			if (!sourceState.equals(projected)) throw new SQLException(
				"staged MariaDB schema did not preserve source durable rows");
			writeRuntimePatchLedger(connection, "mariadb");
			writeLedger(connection, contract, sourceRow, sourceSchema.fingerprint, sourceState);
			Schema sourceAfterSchema = mariaSchema(connection, target.sourceSchema);
			if (!sourceSchema.fingerprint.equals(sourceAfterSchema.fingerprint)) throw new SQLException(
				"MariaDB source schema changed during staged migration");
			String sourceAfter = stateHash(connection, sourceAfterSchema, target.sourceSchema);
			writeEvidence(evidence, contract, sourceRow, sourceSchema.fingerprint,
				sourceState, projected, sourceState, sourceAfter, target.stageSchema);
		} catch (Exception failure) {
			if (stageOwned) target.dropOwnedStageQuietly();
			throw failure;
		}
	}

	private static void applyTransform(Connection connection, String engine,
		String transformationId)
		throws SQLException {
		for (String table : Arrays.asList("curstats", "maxstats", "experience",
			"capped_experience")) {
			boolean levels = "curstats".equals(table) || "maxstats".equals(table);
			int defaultValue = levels ? 1 : 0;
			if ("retro-split-skills-to-current-v1".equals(transformationId)) {
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
			} else if ("core-skills-to-current-v1".equals(transformationId)) {
				if (!"sqlite".equals(engine)) throw new SQLException(
					"core skill migration is only reviewed for SQLite");
				addColumnIfMissing(connection, engine, table, "summoning", defaultValue);
			} else if ("preservation-2023-skills-to-current-v1".equals(transformationId)) {
				if (!"sqlite".equals(engine)) throw new SQLException(
					"initialized Preservation migration is only reviewed for SQLite");
				addColumnIfMissing(connection, engine, table, "summoning", defaultValue);
				addColumnIfMissing(connection, engine, table, "blessing", defaultValue);
			} else {
				throw new SQLException("unreviewed migration transformation: " + transformationId);
			}
		}
		applyCurrentRuntimeSchema(connection, engine);
	}

	private static void applyCurrentRuntimeSchema(Connection connection, String engine)
		throws SQLException {
		try (Statement statement = connection.createStatement()) {
			if ("sqlite".equals(engine)) {
				statement.executeUpdate("CREATE TABLE IF NOT EXISTS equipped (playerID INTEGER NOT NULL, "
					+ "itemID INTEGER NOT NULL)");
				statement.executeUpdate("CREATE TABLE IF NOT EXISTS former_names (dbid INTEGER NOT NULL "
					+ "PRIMARY KEY, playerId INTEGER NOT NULL, formerName VARCHAR(13) NOT NULL "
					+ "DEFAULT '0', changeType TINYINT NOT NULL DEFAULT 0, time INTEGER NOT NULL "
					+ "DEFAULT 0, whoChanged VARCHAR(12) NOT NULL DEFAULT '0', reason VARCHAR(120) "
					+ "NOT NULL DEFAULT '0')");
				addColumnIfMissing(connection, engine, "players", "former_name", "VARCHAR(13) NOT NULL DEFAULT ''");
				addColumnIfMissing(connection, engine, "friends", "friendFormerName", "VARCHAR(13) NOT NULL DEFAULT ''");
				if (!hasColumn(connection, "ignores", "ignoreFormer")) {
					statement.executeUpdate("ALTER TABLE ignores ADD COLUMN ignoreFormer BIGINT(19) NOT NULL DEFAULT 0");
					statement.executeUpdate("CREATE INDEX ignoreFormer ON ignores(ignoreFormer)");
				}
				if (!hasColumn(connection, "logins", "nonce")) {
					statement.executeUpdate("ALTER TABLE logins ADD COLUMN nonce VARCHAR(96)");
					statement.executeUpdate("CREATE UNIQUE INDEX nonce_index ON logins(nonce)");
				}
			} else {
				statement.executeUpdate("CREATE TABLE equipped (playerID INT UNSIGNED NOT NULL, "
					+ "itemID INT UNSIGNED NOT NULL) DEFAULT CHARSET=utf8");
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

	private static void addColumnIfMissing(Connection connection, String engine,
		String table, String column, int defaultValue) throws SQLException {
		if (!hasColumn(connection, table, column))
			addColumn(connection, engine, table, column, defaultValue);
	}

	private static void addColumnIfMissing(Connection connection, String engine,
		String table, String column, String declaration) throws SQLException {
		if (hasColumn(connection, table, column)) return;
		try (Statement statement = connection.createStatement()) {
			statement.executeUpdate("ALTER TABLE " + quote(table) + " ADD COLUMN "
				+ quote(column) + " " + declaration);
		}
	}

	private static boolean hasColumn(Connection connection, String table, String column)
		throws SQLException {
		try (ResultSet result = connection.getMetaData().getColumns(
			null, null, table, column)) {
			return result.next();
		}
	}

	private static void writeLedger(Connection connection, Contract contract,
		SourceRow sourceRow, String sourceSchema, String sourceState) throws SQLException {
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
			statement.setString(1, sourceRow.migrationRowId);
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
				int count = table.columns.size();
				ResultSetMetaData metadata = result.getMetaData();
				int rowCount = 0;
				long encodedBytes = 0;
				long sourceCellBytes = 0;
				while (result.next()) {
					if (++rowCount > MAXIMUM_ROWS_PER_TABLE) throw new SQLException(
						"table exceeds reviewed migration row limit: " + table.name);
					MessageDigest rowDigest = MessageDigest.getInstance("SHA-256");
					for (int index = 1; index <= count; index++) {
						update(rowDigest, "cell\0" + index + "\0jdbc-type\0"
							+ metadata.getColumnType(index) + "\0");
						InputStream opened = result.getBinaryStream(index);
						if (opened == null) {
							if (!result.wasNull()) throw new SQLException(
								"non-null state cell has no binary representation");
							update(rowDigest, "null\0");
						} else try (InputStream input = opened) {
								MessageDigest cellDigest = MessageDigest.getInstance("SHA-256");
								long cellLength = 0;
								byte[] buffer = new byte[65536]; int read;
								while ((read = input.read(buffer)) >= 0) if (read > 0) {
									cellDigest.update(buffer, 0, read); cellLength += read;
									sourceCellBytes += read;
									if (sourceCellBytes > MAXIMUM_SOURCE_CELL_BYTES_PER_TABLE)
										throw new SQLException("table exceeds reviewed source cell byte limit: "
											+ table.name);
								}
								update(rowDigest, "value\0" + cellLength + "\0"
									+ hex(cellDigest.digest()) + "\0");
						}
					}
					String row = hex(rowDigest.digest());
					encodedBytes += row.length() + 1L;
					if (encodedBytes > MAXIMUM_ROW_DIGEST_BYTES_PER_TABLE) throw new SQLException(
						"table exceeds reviewed migration digest limit: " + table.name);
					rows.add(row);
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

	private static void writeEvidence(Path path, Contract contract, SourceRow sourceRow,
		String sourceSchema, String sourceState, String stagedProjection,
		String sourceBefore, String sourceAfter, String stageLocation) throws Exception {
		if (!sourceBefore.equals(sourceAfter)) throw new IOException(
			"source changed while migration evidence was being produced");
		JSONObject evidence = new JSONObject();
		evidence.put("schemaId", "current-base-state-migration-evidence-v1");
		evidence.put("manifestType", "current-base-state-migration-evidence");
		evidence.put("migrationRowId", sourceRow.migrationRowId);
		evidence.put("engine", sourceRow.engine);
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

	private static void requireNoSqliteSidecars(Path source) throws IOException {
		for (String suffix : Arrays.asList("-wal", "-shm", "-journal")) {
			Path sidecar = Paths.get(source.toString() + suffix);
			if (Files.exists(sidecar, LinkOption.NOFOLLOW_LINKS)) throw new IOException(
				"SQLite source has an active journal sidecar; stop it cleanly before migration");
		}
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
				|| !"canonical-public-state-v1".equals(value.getString("targetStateContractId"))) {
				throw new IOException("migration contract identity is unsupported");
			}
			JSONArray rows = value.getJSONArray("supportedSources");
			JSONArray rowIds = value.getJSONArray("migrationRows");
			if (rows.length() != 4 || rowIds.length() != 4) throw new IOException(
				"migration source matrix is incomplete");
			Set<String> expectedRows = new LinkedHashSet<String>();
			for (int index = 0; index < rowIds.length(); index++)
				expectedRows.add(rowIds.getString(index));
			Set<String> actualRows = new LinkedHashSet<String>();
			for (int index = 0; index < rows.length(); index++) {
				JSONObject row = rows.getJSONObject(index);
				requireKeys(row, ENGINE_KEYS, "source row");
				actualRows.add(row.getString("migrationRowId"));
			}
			if (!expectedRows.equals(actualRows)) throw new IOException(
				"migrationRows differs from the compiled source rows");
			requireKeys(value.getJSONObject("transformations"), TRANSFORM_KEYS,
				"transformations");
			JSONObject limits = value.getJSONObject("resourceLimits");
			requireKeys(limits, RESOURCE_LIMIT_KEYS, "resource limits");
			if (limits.getLong("maximumSqliteSourceBytes") != MAXIMUM_SQLITE_SOURCE_BYTES
				|| limits.getInt("maximumRowsPerTable") != MAXIMUM_ROWS_PER_TABLE
				|| limits.getLong("maximumEncodedRowDigestBytesPerTable")
					!= MAXIMUM_ROW_DIGEST_BYTES_PER_TABLE
				|| limits.getLong("maximumSourceCellBytesPerTable")
					!= MAXIMUM_SOURCE_CELL_BYTES_PER_TABLE) throw new IOException(
				"migration resource limits differ from compiled limits");
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
		private SourceRow matchSource(String engine, String actual) throws IOException {
			JSONArray rows = document.getJSONArray("supportedSources");
			for (int index = 0; index < rows.length(); index++) {
				JSONObject row = rows.getJSONObject(index);
				String expected = row.getString("sourceSchemaFingerprint");
				if (engine.equals(row.getString("engine")) && HASH.matcher(expected).matches()
					&& expected.equals(actual)) return new SourceRow(row);
			}
			throw new IOException(
				"unsupported or customized " + engine + " source schema: " + actual);
		}
	}

	private static final class SourceRow {
		private final String migrationRowId, engine, transformationId;
		private SourceRow(JSONObject row) {
			this.migrationRowId = row.getString("migrationRowId");
			this.engine = row.getString("engine");
			this.transformationId = row.getString("transformationId");
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

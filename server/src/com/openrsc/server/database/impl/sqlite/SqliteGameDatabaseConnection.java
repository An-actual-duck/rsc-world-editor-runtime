package com.openrsc.server.database.impl.sqlite;

import com.openrsc.server.Server;
import com.openrsc.server.database.DatabaseType;
import com.openrsc.server.database.JDBCDatabaseConnection;
import com.openrsc.server.util.SystemUtil;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.File;
import java.io.IOException;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

public class SqliteGameDatabaseConnection extends JDBCDatabaseConnection {
    public static final String DB_FOLDER = "inc/sqlite/";
    private final Logger LOGGER = LogManager.getLogger();
    private Connection connection;
    private Statement statement;
    private boolean connected;
    private final Server server;
    private String selectedDatabaseUrl;

    public SqliteGameDatabaseConnection(Server server) {
        this.server = server;
    }

    private String getDBPath(String dbName) {
        return DB_FOLDER + dbName + ".db";
    }

    @Override
    public synchronized boolean open() {
        // Close the old connection before attempting to open a new connection.
        close();

        final String dbName = server.getConfig().DB_NAME;
        final Path managed;
        final String databaseUrl;
        try {
            managed = CurrentBaseStateLocation.resolve(dbName);
            databaseUrl = managed == null ? "jdbc:sqlite:" + getDBPath(dbName)
                : "jdbc:sqlite:" + managed.toUri().toASCIIString() + "?mode=rw";
            if (selectedDatabaseUrl != null && !selectedDatabaseUrl.equals(databaseUrl)) {
                throw new IOException("SQLite location changed across reconnect");
            }
        } catch (IOException | IllegalArgumentException unsafe) {
            throw new IllegalStateException("SQLite state location refused", unsafe);
        }
        File dbFile = managed == null ? new File(getDBPath(dbName)) : managed.toFile();
        if(!dbFile.exists()) {
            LOGGER.error("Database file {} does not exist.", dbFile.getAbsolutePath());
            SystemUtil.exit(1);
        }

        try {
            connection = DriverManager.getConnection(databaseUrl);
            selectedDatabaseUrl = databaseUrl;
            statement = getConnection().createStatement();
            connected = checkConnection();
        } catch (final SQLException e) {
            LOGGER.catching(e);
            connected = false;
        }

        if(isConnected()) {
            LOGGER.info(managed == null
                ? server.getName() + " : " + server.getName() + " - Connected to SQLite @ " + getDBPath(dbName) + "!"
                : "Connected to private external Current Base SQLite state");
        } else {
            LOGGER.error("Unable to connect to SQLite");
            SystemUtil.exit(1);
        }

        return isConnected();
    }

    @Override
    public synchronized void close() {
        try {
            if(statement != null) {
                statement.close();
            }
        } catch (final SQLException e) {
            LOGGER.catching(e);
        }
        try {
            if(getConnection() != null) {
                getConnection().close();
            }
        } catch (final SQLException e) {
            LOGGER.catching(e);
        }
        connected = false;
        statement = null;
        connection = null;
    }

    @Override
    public DatabaseType getDatabaseType() {
        return DatabaseType.SQLITE;
    }

    @Override
    protected Statement getStatement() {
        return statement;
    }

    @Override
    public Connection getConnection() {
        return connection;
    }

    @Override
    protected boolean checkConnection() {
        try {
            getStatement().executeQuery("SELECT CURRENT_DATE");
            return true;
        } catch (final SQLException e) {
            return false;
        }
    }

    @Override
    public boolean isConnected() {
        return connected;
    }
}

package com.openrsc.server.database.impl.sqlite;

import com.openrsc.server.CurrentCompositionIdentity;
import com.openrsc.server.ServerConfiguration;
import com.openrsc.server.content.worldedit.WorldBuilderMode;
import com.openrsc.server.content.worldedit.WorldEditStorageContext;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;

/** Provider-owned location boundary for mutable Current Base SQLite state. */
public final class CurrentBaseStateLocation {
    public static final String PROPERTY = "openrsc.currentBaseStateRoot";
    public static final String DATABASE = "current_base.db";
    public static final String AUTHORING_PROPERTY = "openrsc.currentBaseAuthoringStateRoot";

    private CurrentBaseStateLocation() { }

    /** Null selects the unchanged historical layout only for an unconfigured non-Base runtime. */
    public static Path resolve(String databaseName) throws IOException {
        if (System.getProperty(AUTHORING_PROPERTY) != null) throw new IOException(
            "Base authoring state requires validated adaptive World Builder configuration");
        return resolveSelected(databaseName, false);
    }

    public static Path resolve(ServerConfiguration configuration) throws IOException {
        boolean authoring = System.getProperty(AUTHORING_PROPERTY) != null;
        if (authoring) {
            if (System.getProperty(PROPERTY) != null) throw new IOException(
                "installed and authoring Base state roots are mutually exclusive");
            if (!configuration.WORLD_BUILDER_MODE || !configuration.WORLD_BUILDER_ADAPTIVE_MODE)
                throw new IOException("Base authoring state requires explicit adaptive World Builder mode");
            if (configuration.WORLD_BUILDER_CONTENT_BUNDLE_PATH != null
                && !configuration.WORLD_BUILDER_CONTENT_BUNDLE_PATH.trim().isEmpty())
                throw new IOException("Base authoring state requires native public content without a custom overlay");
            WorldBuilderMode.validate(configuration);
            String workspace = System.getProperty(WorldEditStorageContext.WORKSPACE_PROPERTY, "");
            Path expected = Paths.get(workspace).resolve("working/authoring-state");
            if (workspace.isEmpty() || !expected.isAbsolute()
                || !expected.equals(expected.normalize()) || !expected.equals(expected.toRealPath())
                || !expected.toString().equals(System.getProperty(AUTHORING_PROPERTY)))
                throw new IOException("Base authoring state must be the canonical workspace working/authoring-state directory");
        }
        return resolveSelected(configuration.DB_NAME, authoring);
    }

    private static Path resolveSelected(String databaseName, boolean authoring) throws IOException {
        CurrentCompositionIdentity identity = CurrentCompositionIdentity.current();
        boolean currentBase = identity.isEnabled()
            && "current-base-v1".equals(identity.value("variantId"));
        String property = authoring ? AUTHORING_PROPERTY : PROPERTY;
        String configured = System.getProperty(property);
        if (!currentBase) {
            if (configured != null) throw new IOException(
                "managed state root requires an initialized Current Base composition");
            return null;
        }
        if (configured == null || configured.isEmpty()) throw new IOException(
            property + " is required by Current Base; no in-runtime database fallback is allowed");
        String expectedName = authoring ? WorldBuilderMode.DATABASE_NAME : "current_base";
        if (!expectedName.equals(databaseName)) throw new IOException(
            "Current Base requires the canonical " + expectedName + " database name");
        Path root = Paths.get(configured);
        if (!root.isAbsolute() || !root.equals(root.normalize())
            || !root.equals(root.toRealPath())) throw new IOException(
                "managed state root must be an existing canonical absolute directory");
        requirePrivate(root, true);
        Path working = Paths.get("").toRealPath();
        Path artifact;
        try {
            artifact = Paths.get(CurrentBaseStateLocation.class.getProtectionDomain()
                .getCodeSource().getLocation().toURI()).toRealPath();
        } catch (Exception invalid) {
            throw new IOException("cannot establish the runtime artifact location", invalid);
        }
        if (Files.isRegularFile(artifact, LinkOption.NOFOLLOW_LINKS)) artifact = artifact.getParent();
        requireDisjoint(root, working);
        requireDisjoint(root, artifact);
        if (authoring && Files.exists(root.resolve(DATABASE), LinkOption.NOFOLLOW_LINKS))
            throw new IOException("Base authoring state must not share an installed database directory");
        String filename = authoring ? WorldBuilderMode.DATABASE_NAME + ".db" : DATABASE;
        Path database = root.resolve(filename);
        requirePrivate(database, false);
        // Recovery journals are legitimate live state, but never aliases to another file.
        for (String suffix : new String[] {"-journal", "-wal", "-shm"}) {
            Path sidecar = root.resolve(filename + suffix);
            if (Files.exists(sidecar, LinkOption.NOFOLLOW_LINKS)) requirePrivate(sidecar, false);
        }
        return database;
    }

    private static void requireDisjoint(Path state, Path runtime) throws IOException {
        if (state.startsWith(runtime) || runtime.startsWith(state)) throw new IOException(
            "managed state root must be disjoint from runtime artifacts and working directory");
    }

    private static void requirePrivate(Path path, boolean directory) throws IOException {
        if (Files.isSymbolicLink(path) || (directory
            ? !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
            : !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))) throw new IOException(
                "managed state path is missing, linked, or has the wrong file type");
        try {
            int mode = ((Number)Files.getAttribute(path, "unix:mode", LinkOption.NOFOLLOW_LINKS)).intValue();
            if ((mode & 07777) != (directory ? 0700 : 0600)) throw new IOException(
                "managed state requires directory mode 0700 and file mode 0600");
            if (!directory && ((Number)Files.getAttribute(path, "unix:nlink",
                LinkOption.NOFOLLOW_LINKS)).longValue() != 1L) throw new IOException(
                    "managed state files must not have hard-link aliases");
        } catch (UnsupportedOperationException unsupported) {
            throw new IOException("managed state requires supported POSIX private-file checks", unsupported);
        }
    }
}

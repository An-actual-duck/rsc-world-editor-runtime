package com.openrsc.server.database.impl.mysql;

import com.openrsc.server.Server;
import com.openrsc.server.database.GameLogger;
import com.openrsc.server.database.impl.mysql.queries.Query;
import com.openrsc.server.database.impl.mysql.queries.ResultQuery;
import com.openrsc.server.util.ServerAwareThreadFactory;
import com.openrsc.server.util.SystemUtil;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class MySqlGameLogger extends GameLogger {

	/**
	 * The asynchronous logger.
	 */
	private static final Logger LOGGER = LogManager.getLogger();

	private volatile AtomicBoolean running;
	private final BlockingQueue<Query> queries;
	private final Server server;
	private ScheduledExecutorService scheduledExecutor;
	private final MySqlGameDatabase database;
	private volatile Throwable installedWriteFailure;

	public MySqlGameLogger(final Server server, final MySqlGameDatabase database) {
		this.server = server;

		running = new AtomicBoolean(false);
		queries = new ArrayBlockingQueue<>(10000);
		// TODO: Implement GameLogger into the database driver.
		if (database == null) {
			LOGGER.error("GameDatabase provided was null or not a MySqlGameDatabase.");
			SystemUtil.exit(1);
		}
		this.database = database;
	}

	public final Server getServer() {
		return server;
	}

	public void start() {
		synchronized (running) {
			running.set(true);
			scheduledExecutor = Executors.newSingleThreadScheduledExecutor(
					new ServerAwareThreadFactory(
							server.getName() + " : DatabaseLogging",
							server.getConfig()
					)
			);
			scheduledExecutor.scheduleAtFixedRate(this, 0, 50, TimeUnit.MILLISECONDS);
		}
	}

	public void stop() {
		if (com.openrsc.server.CurrentInstalledLaunch.current() != null) {
			// Do not hold running while waiting for a task that needs that monitor.
			com.openrsc.server.InstalledShutdownDrain.finish(scheduledExecutor, () -> {
				synchronized (running) {
					if (installedWriteFailure != null)
						throw new IllegalStateException("An installed database write previously failed", installedWriteFailure);
					while (!queries.isEmpty()) {
						if (!getDatabase().getConnection().isConnected())
							throw new IllegalStateException("Installed database disconnected before final drain");
						pollNextQuery();
					}
					running.set(false);
				}
			});
			scheduledExecutor = null;
			return;
		}
		synchronized (running) {
			scheduledExecutor.shutdown();
			try {
				final boolean terminationResult = scheduledExecutor.awaitTermination(1, TimeUnit.MINUTES);
				if (!terminationResult) {
					LOGGER.error("MySqlGameLogger thread termination failed");
					List<Runnable> skippedTasks = scheduledExecutor.shutdownNow();
					LOGGER.error("{} task(s) never commenced execution", skippedTasks.size());
				}
			} catch (final InterruptedException e) {
				LOGGER.error("MySqlGameLogger thread interrupted during stop()");
			}
			clearQueries();
			scheduledExecutor = null;
			running.set(false);
		}
	}

	private void clearQueries() {
		queries.clear();
	}

	@Override
	public void run() {
		synchronized (running) {
			if (running.get()) {
				while (queries.size() > 0 && getDatabase().getConnection().isConnected()) {
					pollNextQuery();
				}
			}
		}
	}

	protected void pollNextQuery() {
		if (com.openrsc.server.CurrentInstalledLaunch.current() != null) {
			Query query = queries.peek();
			runQuery(query);
			if (query != null) queries.remove(query);
			return;
		}
		runQuery(queries.poll());
	}

	protected void runQuery(final Query query) {
		try {
			if (query != null) {
				if (query instanceof ResultQuery) {
					final ResultQuery rq = (ResultQuery) query;
					try (final PreparedStatement statement = rq.prepareStatement(getDatabase().getConnection().getConnection());
						 final ResultSet result = statement.executeQuery();) {
						rq.onResult(result);
					}
				} else {
					try (final PreparedStatement statement = query.prepareStatement(getDatabase().getConnection().getConnection());) {
						statement.execute();
					}
				}
			}
		/*} catch (final GameDatabaseException ex) {
			LOGGER.catching(ex);
		*/} catch (final Exception ex) {
			if (com.openrsc.server.CurrentInstalledLaunch.current() != null) {
				installedWriteFailure = ex;
				throw new IllegalStateException("Installed database write failed", ex);
			}
			LOGGER.error("Error executing runQuery", ex);
			if (server.getDiscordService() != null && server.getConfig().WANT_DISCORD_GENERAL_LOGGING) {
				server.getDiscordService().errorLogStackTrace(ex);
			}
		}
	}

	// Runs a query on the database thread. This is mostly useful for non-critical data like game logs that we don't make further calculations on.
	public void addQuery(final Query query) {
		if (com.openrsc.server.CurrentInstalledLaunch.current() != null) {
			synchronized (running) {
				if (!running.get()) throw new IllegalStateException("Installed database writer is stopped");
				queries.add(query);
			}
			return;
		}
		if (!running.get()) {
			return;
		}
		queries.add(query);
	}

	// Runs a query on whatever program thread initiated the request. This is mostly useful for playing loading/saving to ensure data is returned.
	public void run(final Query query) {
		runQuery(query);
	}

	private MySqlGameDatabase getDatabase() {
		return database;
	}
}

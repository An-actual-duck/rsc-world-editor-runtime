package com.openrsc.server;

/** Normal installed Current Base server; no class initializer starts logging. */
public final class CurrentBaseInstalledServer {
    private CurrentBaseInstalledServer() { }
    public static void main(String[] args) {
        try {
            CurrentInstalledLaunch launch = CurrentInstalledLaunch.open(args, "server", CurrentBaseInstalledServer.class);
            launch.configure();
            CurrentCompositionIdentity.initializeFromSystemProperties();
            Server server = Server.startServer(launch.bound("configuration").toString());
            if (!server.isRunning()) throw new IllegalStateException("Installed server did not become ready");
            java.util.concurrent.atomic.AtomicBoolean stopStarted = new java.util.concurrent.atomic.AtomicBoolean();
            Runnable stopOnce = () -> {
                if (stopStarted.compareAndSet(false, true) && server.isRunning()) server.stop();
            };
            Runtime.getRuntime().addShutdownHook(new Thread(stopOnce, "installed-server-save-on-exit"));
            launch.ready();
            while (server.isRunning()) {
                if (launch.shutdownRequested()) { stopOnce.run(); break; }
                server.checkShutdown();
                Thread.sleep(100);
            }
            System.exit(0);
        } catch (Throwable failure) {
            while (failure.getCause() != null && failure.getCause() != failure) failure = failure.getCause();
            System.err.println("Installed server startup/control refused: " + failure.getClass().getSimpleName());
            System.exit(2);
        }
    }
}

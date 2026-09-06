package com.openrsc.server;

/** Disposable verifier child: acquire its lifetime lease before Server class initialization. */
public final class CurrentBaseVerifierServer {
    private static VerifierLifetime lifetime;
    public static void main(String[] arguments) {
        try {
            lifetime = VerifierLifetime.child(arguments, "server");
            Thread watcher = new Thread(() -> {
                try { System.in.read(); } catch (java.io.IOException ignored) { }
                System.exit(2);
            }, "verifier-server-parent-pipe");
            watcher.setDaemon(true); watcher.start();
            lifetime.requireOpen();
            Server.main(new String[] {"current-base.conf"});
        } catch (Exception failure) {
            System.err.println("Verifier server child refused: " + failure.getClass().getSimpleName());
            System.exit(2);
        }
    }
}

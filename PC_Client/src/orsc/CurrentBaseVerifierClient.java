package orsc;

/** Disposable verifier child: acquire its lifetime lease before client initialization. */
public final class CurrentBaseVerifierClient {
    private static VerifierLifetime lifetime;
    public static void main(String[] arguments) {
        try {
            lifetime = VerifierLifetime.child(arguments, "client");
            Thread watcher = new Thread(() -> {
                try { System.in.read(); } catch (java.io.IOException ignored) { }
                System.exit(2);
            }, "verifier-client-parent-pipe");
            watcher.setDaemon(true); watcher.start();
            lifetime.requireOpen();
            OpenRSC.main(new String[0]);
        } catch (Exception failure) {
            System.err.println("Verifier client child refused: " + failure.getClass().getSimpleName());
            System.exit(2);
        }
    }
}

package orsc;

/** Normal, manually authenticated installed Current Base desktop client. */
public final class CurrentBaseInstalledClient {
    private CurrentBaseInstalledClient() { }
    public static void main(String[] args) {
        try {
            CurrentInstalledLaunch launch = CurrentInstalledLaunch.open(args, "client", CurrentBaseInstalledClient.class);
            launch.configure();
            OpenRSC.main(new String[0]);
            long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(120);
            while (!launch.hasWindowShown()) {
                if (System.nanoTime() > deadline) throw new IllegalStateException("Installed client window readiness timed out");
                Thread.sleep(100);
            }
            launch.ready();
            while (true) {
                if (launch.shutdownRequested()) {
                    javax.swing.SwingUtilities.invokeAndWait(() -> ScaledWindow.getInstance().dispatchEvent(
                        new java.awt.event.WindowEvent(ScaledWindow.getInstance(), java.awt.event.WindowEvent.WINDOW_CLOSING)));
                    break;
                }
                Thread.sleep(100);
            }
        } catch (Throwable failure) {
            System.err.println("Installed client startup/control refused: " + failure.getClass().getSimpleName());
            System.exit(2);
        }
    }
}

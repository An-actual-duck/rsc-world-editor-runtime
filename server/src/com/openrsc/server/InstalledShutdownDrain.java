package com.openrsc.server;

import java.util.concurrent.*;

/** Bounded final writer barrier; callers retain process ownership on failure. */
public final class InstalledShutdownDrain {
    private InstalledShutdownDrain() { }

    public static void finish(ExecutorService executor, Runnable drain) {
        finish(executor, drain, 60, TimeUnit.SECONDS);
    }

    static void finish(ExecutorService executor, Runnable drain, long timeout, TimeUnit unit) {
        long deadline = System.nanoTime() + unit.toNanos(timeout);
        Future<?> completion = executor.submit(drain);
        executor.shutdown();
        try {
            completion.get(Math.max(1, deadline - System.nanoTime()), TimeUnit.NANOSECONDS);
            if (!executor.awaitTermination(Math.max(1, deadline - System.nanoTime()), TimeUnit.NANOSECONDS))
                throw new IllegalStateException("Installed writer termination exceeded its deadline");
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Installed writer drain was interrupted", failure);
        } catch (ExecutionException | TimeoutException failure) {
            throw new IllegalStateException("Installed writer drain did not complete cleanly", failure);
        }
    }
}

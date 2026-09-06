#!/usr/bin/env python3
"""Deterministic final-writer ordering, failure propagation and bounded ownership."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class InstalledShutdownDrainTest(unittest.TestCase):
    def test_queued_writes_failure_and_timeout_barriers(self):
        with tempfile.TemporaryDirectory(prefix="installed-drain-") as temporary:
            root = Path(temporary)
            source = root / "DrainProbe.java"
            source.write_text('''
package com.openrsc.server;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public class DrainProbe {
  public static void main(String[] args) throws Exception {
    ExecutorService success = Executors.newSingleThreadExecutor();
    AtomicInteger state = new AtomicInteger();
    success.submit(() -> state.set(1));
    InstalledShutdownDrain.finish(success, () -> {
      if (state.get() != 1) throw new AssertionError("prior write not complete");
      state.set(2);
    });
    if (state.get() != 2 || !success.isTerminated()) throw new AssertionError("final write not complete");

    ExecutorService failed = Executors.newSingleThreadExecutor();
    try {
      InstalledShutdownDrain.finish(failed, () -> { throw new IllegalStateException("invented write failure"); });
      throw new AssertionError("failed write reported clean");
    } catch (IllegalStateException expected) {
      if (!(expected.getCause() instanceof ExecutionException)) throw expected;
    } finally { failed.shutdown(); failed.awaitTermination(5, TimeUnit.SECONDS); }

    CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
    ExecutorService slow = Executors.newSingleThreadExecutor();
    slow.submit(() -> { entered.countDown(); try { release.await(); }
      catch (InterruptedException failure) { throw new AssertionError("must not force-stop writer", failure); } });
    entered.await();
    try {
      InstalledShutdownDrain.finish(slow, () -> state.set(3), 20, TimeUnit.MILLISECONDS);
      throw new AssertionError("unresolved writer reported clean");
    } catch (IllegalStateException expected) {
      if (!(expected.getCause() instanceof TimeoutException) || slow.isTerminated()) throw expected;
    } finally { release.countDown(); slow.awaitTermination(5, TimeUnit.SECONDS); }
    if (state.get() != 3) throw new AssertionError("uncertain writer work was discarded");
    System.out.println("PASS queued ordering, error propagation and bounded uncertain ownership");
  }
}
''', encoding="utf-8")
            subprocess.run(["javac", "-source", "8", "-target", "8", "-d", str(root), str(source),
                str(ROOT / "server/src/com/openrsc/server/InstalledShutdownDrain.java")], check=True, capture_output=True)
            result = subprocess.run(["java", "-cp", str(root), "com.openrsc.server.DrainProbe"],
                check=True, capture_output=True, text=True, timeout=15)
            self.assertIn("PASS queued ordering", result.stdout)


if __name__ == "__main__":
    unittest.main()

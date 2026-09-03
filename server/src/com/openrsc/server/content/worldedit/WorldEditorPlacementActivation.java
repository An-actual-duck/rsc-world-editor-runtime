package com.openrsc.server.content.worldedit;

/** Best-effort transactional replacement for one package's live placements. */
final class WorldEditorPlacementActivation {
	interface Runtime<T> {
		void retire();
		void populate(T value);
	}

	private WorldEditorPlacementActivation() {
	}

	static <T> void replace(T current, T published, Runtime<T> runtime) {
		if (current == null || published == null || runtime == null) {
			throw new IllegalArgumentException(
				"Live placement replacement requires both packages and a runtime.");
		}
		try {
			runtime.retire();
			runtime.populate(published);
		} catch (RuntimeException failure) {
			rollback(current, runtime, failure);
			throw failure;
		}
	}

	private static <T> void rollback(
		T current, Runtime<T> runtime, Throwable failure) {
		try {
			runtime.retire();
			runtime.populate(current);
		} catch (RuntimeException rollbackFailure) {
			failure.addSuppressed(rollbackFailure);
		}
	}
}

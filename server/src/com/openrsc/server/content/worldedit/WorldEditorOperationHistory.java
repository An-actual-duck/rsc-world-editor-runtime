package com.openrsc.server.content.worldedit;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Bounded, session-local history for authoritative editor operations.
 *
 * <p>Consecutive batches sharing a positive token are coalesced into one
 * operation. Undo and redo verify the complete expected state before moving a
 * history entry, so an unrecorded mutation can never be overwritten.</p>
 */
public final class WorldEditorOperationHistory<K,V> {
	public static final int MAX_OPERATIONS = 64;
	public static final int MAX_STATE_REFERENCES = 65536;

	private final Deque<Entry<K,V>> undo = new ArrayDeque<Entry<K,V>>();
	private final Deque<Entry<K,V>> redo = new ArrayDeque<Entry<K,V>>();
	private int stateReferences;

	public synchronized void clear() {
		undo.clear();
		redo.clear();
		stateReferences = 0;
	}

	public synchronized boolean canUndo() { return !undo.isEmpty(); }
	public synchronized boolean canRedo() { return !redo.isEmpty(); }

	public synchronized void record(
		long token, String label, List<Change<K,V>> changes) {
		if (token <= 0) throw new IllegalArgumentException(
			"Editor history token must be positive.");
		if (label == null || label.trim().isEmpty()) throw new IllegalArgumentException(
			"Editor history label is required.");
		if (changes == null || changes.isEmpty()) return;

		Entry<K,V> entry = undo.peekLast();
		boolean coalescing = redo.isEmpty()
			&& entry != null && entry.token == token;
		if (!coalescing) {
			entry = new Entry<K,V>(token, label.trim());
			for (Change<K,V> change : changes) entry.merge(change);
			if (entry.changes.isEmpty()) return;
			clearRedo();
			undo.addLast(entry);
			stateReferences += entry.changes.size();
			trim();
			return;
		} else if (!entry.label.equals(label.trim())) {
			throw new IllegalStateException(
				"Editor history token was reused for a different operation.");
		}

		int previousSize = entry.changes.size();
		for (Change<K,V> change : changes) entry.merge(change);
		stateReferences += entry.changes.size() - previousSize;
		if (entry.changes.isEmpty()) undo.removeLast();
		trim();
	}

	public synchronized List<Change<K,V>> nextUndoChanges() {
		Entry<K,V> entry = undo.peekLast();
		return entry == null ? Collections.<Change<K,V>>emptyList()
			: entry.snapshot(false);
	}

	public synchronized List<Change<K,V>> nextRedoChanges() {
		Entry<K,V> entry = redo.peekLast();
		return entry == null ? Collections.<Change<K,V>>emptyList()
			: entry.snapshot(true);
	}

	public synchronized Action<K,V> undo(Map<K,V> current) {
		return apply(undo, redo, current, false);
	}

	public synchronized Action<K,V> redo(Map<K,V> current) {
		return apply(redo, undo, current, true);
	}

	private Action<K,V> apply(
		Deque<Entry<K,V>> source,
		Deque<Entry<K,V>> destination,
		Map<K,V> current,
		boolean forward) {
		Entry<K,V> entry = source.peekLast();
		if (entry == null) throw new IllegalStateException(
			forward ? "There is nothing to redo." : "There is nothing to undo.");
		if (current == null) throw new IllegalArgumentException(
			"Current editor state is required.");
		for (Change<K,V> change : entry.changes.values()) {
			V expected = forward ? change.before : change.after;
			if (!current.containsKey(change.key)
				|| !Objects.equals(current.get(change.key), expected)) {
				throw new IllegalStateException(
					"Editor state changed outside this history; undo/redo was refused.");
			}
		}
		source.removeLast();
		destination.addLast(entry);
		return new Action<K,V>(entry.label, entry.snapshot(forward),
			!undo.isEmpty(), !redo.isEmpty());
	}

	private void clearRedo() {
		for (Entry<K,V> entry : redo) stateReferences -= entry.changes.size();
		redo.clear();
	}

	private void trim() {
		while (undo.size() > MAX_OPERATIONS
			|| stateReferences > MAX_STATE_REFERENCES) {
			Entry<K,V> removed = undo.removeFirst();
			stateReferences -= removed.changes.size();
		}
	}

	public static final class Change<K,V> {
		public final K key;
		public final V before;
		public final V after;

		private Change(K key, V before, V after) {
			this.key = Objects.requireNonNull(key, "key");
			this.before = Objects.requireNonNull(before, "before");
			this.after = Objects.requireNonNull(after, "after");
		}

		public static <K,V> Change<K,V> of(K key, V before, V after) {
			return new Change<K,V>(key, before, after);
		}
	}

	public static final class Action<K,V> {
		public final String label;
		public final List<Change<K,V>> changes;
		public final boolean canUndo;
		public final boolean canRedo;

		private Action(
			String label, List<Change<K,V>> changes,
			boolean canUndo, boolean canRedo) {
			this.label = label;
			this.changes = changes;
			this.canUndo = canUndo;
			this.canRedo = canRedo;
		}
	}

	private static final class Entry<K,V> {
		final long token;
		final String label;
		final LinkedHashMap<K,Change<K,V>> changes =
			new LinkedHashMap<K,Change<K,V>>();

		Entry(long token, String label) {
			this.token = token;
			this.label = label;
		}

		void merge(Change<K,V> incoming) {
			if (incoming == null) throw new IllegalArgumentException(
				"Editor history change is required.");
			Change<K,V> existing = changes.get(incoming.key);
			if (existing == null) {
				if (!incoming.before.equals(incoming.after))
					changes.put(incoming.key, incoming);
				return;
			}
			if (!existing.after.equals(incoming.before)) throw new IllegalStateException(
				"Editor history batches do not form one continuous operation.");
			if (existing.before.equals(incoming.after)) changes.remove(incoming.key);
			else changes.put(incoming.key,
				Change.of(incoming.key, existing.before, incoming.after));
		}

		List<Change<K,V>> snapshot(boolean forward) {
			List<Change<K,V>> result =
				new ArrayList<Change<K,V>>(changes.size());
			for (Change<K,V> change : changes.values()) {
				result.add(forward ? change
					: Change.of(change.key, change.after, change.before));
			}
			return Collections.unmodifiableList(result);
		}
	}
}

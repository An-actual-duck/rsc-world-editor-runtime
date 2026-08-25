package com.openrsc.server.content.worldedit;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.zip.GZIPInputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** Server-side semantic verifier for the client-owned NPC animation registry. */
final class AdaptiveWorldBuilderNpcAnimationRegistry {
	private static final long MAX_BYTES = 256L * 1024L * 1024L;
	private static final Pattern NAME =
		Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
	private static final Pattern SHA = Pattern.compile("[0-9a-f]{64}");
	private static final Set<String> ROOT_KEYS = set(
		"schemaVersion", "manifestType", "animations");
	private static final Set<String> RECORD_KEYS = set(
		"animationId", "name", "category", "charColour", "blueMask",
		"genderModel", "hasCombatFrames", "hasSpecialCombatFrames",
		"requiredFrameCount", "customSpriteSubspace", "customSpriteEntry",
		"customEntrySha256", "authenticBaseSpriteId",
		"authenticFrameSha256s");

	private AdaptiveWorldBuilderNpcAnimationRegistry() {
	}

	static void validate(Path registry, Path customArchive, Path authenticArchive)
		throws IOException {
		String text = new String(Files.readAllBytes(registry), StandardCharsets.UTF_8);
		AdaptiveWorldBuilderProjectContentBundle.validateStrictJson(text);
		JSONObject document = new JSONObject(text);
		requireKeys(document, ROOT_KEYS);
		if (integer(document, "schemaVersion") != 1
			|| !"world-builder-npc-animation-registry".equals(document.opt("manifestType"))) {
			throw new IOException("NPC animation registry identity is unsupported");
		}
		Map<String,Integer> frames = osarFrames(customArchive);
		JSONArray rows = document.optJSONArray("animations");
		if (rows == null || rows.length() < 1 || rows.length() > 65536) {
			throw new IOException("NPC animation registry is empty or too large");
		}
		int previous = -1;
		for (int index = 0; index < rows.length(); index++) {
			JSONObject row = rows.optJSONObject(index);
			if (row == null) throw new IOException("NPC animation row is not an object");
			requireKeys(row, RECORD_KEYS);
			int id = bounded(row, "animationId", 0, 65535);
			if (id <= previous) throw new IOException("NPC animation IDs are not sorted and unique");
			previous = id;
			String name = name(row, "name"), category = name(row, "category");
			if (!category.equals(name(row, "customSpriteSubspace"))
				|| !name.equals(name(row, "customSpriteEntry"))) {
				throw new IOException("NPC animation custom lookup differs from category/name");
			}
			if (!SHA.matcher(text(row, "customEntrySha256")).matches()) {
				throw new IOException("NPC animation custom entry hash is invalid");
			}
			integer(row, "charColour"); integer(row, "blueMask"); integer(row, "genderModel");
			boolean combat = bool(row, "hasCombatFrames");
			boolean special = bool(row, "hasSpecialCombatFrames");
			if (special && !combat) throw new IOException("NPC special frames require combat frames");
			int count = bounded(row, "requiredFrameCount", 1, 27);
			int expected = 15 + (combat ? 3 : 0) + (special ? 9 : 0);
			if (count != expected || !Integer.valueOf(count).equals(frames.get(category + "\0" + name))) {
				throw new IOException("NPC animation frames disagree with renderer semantics");
			}
			int base = bounded(row, "authenticBaseSpriteId", 0, 65535);
			JSONArray hashes = row.optJSONArray("authenticFrameSha256s");
			if (hashes == null || hashes.length() != count) {
				throw new IOException("NPC authentic animation inventory is incomplete");
			}
			validateAuthentic(authenticArchive, base, hashes);
		}
	}

	private static Map<String,Integer> osarFrames(Path archive) throws IOException {
		byte[] bytes;
		try (InputStream input = new GZIPInputStream(Files.newInputStream(archive))) {
			bytes = read(input, MAX_BYTES);
		}
		ByteBuffer input = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN);
		Map<String,Integer> result = new HashMap<String,Integer>();
		Set<String> spaces = new HashSet<String>();
		try {
			int spaceCount = input.get() & 0xff;
			if (spaceCount < 1) throw new IOException("NPC custom archive is empty");
			for (int s = 0; s < spaceCount; s++) {
				String space = archiveName(input);
				if (!spaces.add(space)) throw new IOException("Duplicate NPC custom subspace");
				int entries = input.getShort() & 0xffff;
				for (int e = 0; e < entries; e++) {
					String name = archiveName(input); int type = input.get() & 0xff;
					if (type > 4) throw new IOException("NPC custom sprite type is invalid");
					if (type >= 1 && type <= 3) input.get();
					int frames = input.get() & 0xff;
					if (frames < 1 || result.put(space + "\0" + name,
						Integer.valueOf(frames)) != null) throw new IOException("NPC custom entry is empty or duplicated");
					int colours = (input.get() & 0xff) + 1;
					input.position(input.position() + colours * 3);
					for (int f = 0; f < frames; f++) {
						int width = input.getShort() & 0xffff, height = input.getShort() & 0xffff;
						int shifted = input.get() & 0xff; input.getShort(); input.getShort();
						int boundWidth = input.getShort() & 0xffff, boundHeight = input.getShort() & 0xffff;
						long pixels = (long)width * height;
						if (width < 1 || height < 1 || shifted > 1
							|| pixels > 16777216L || input.remaining() < pixels) {
							throw new IOException("NPC custom sprite frame is unsafe");
						}
						for (long p = 0; p < pixels; p++) if ((input.get() & 0xff) >= colours) {
							throw new IOException("NPC custom sprite palette index is invalid");
						}
					}
				}
			}
		} catch (java.nio.BufferUnderflowException malformed) {
			throw new IOException("NPC custom sprite archive is truncated", malformed);
		}
		if (input.hasRemaining()) throw new IOException("NPC custom sprite archive has trailing bytes");
		return result;
	}

	private static void validateAuthentic(Path archive, int base, JSONArray hashes)
		throws IOException {
		try (ZipFile zip = new ZipFile(archive.toFile())) {
			for (int index = 0; index < hashes.length(); index++) {
				String expected = hashes.optString(index, "");
				if (!SHA.matcher(expected).matches() || base + index > 65535) {
					throw new IOException("NPC authentic frame identity is invalid");
				}
				int id = base + index; ZipEntry entry = zip.getEntry(String.valueOf(id));
				if (entry == null) entry = zip.getEntry("sprites/" + id + ".dat");
				if (entry == null || entry.isDirectory() || entry.getSize() < 1L
					|| entry.getSize() > MAX_BYTES) throw new IOException("NPC authentic frame is missing");
				try (InputStream input = zip.getInputStream(entry)) {
					if (!expected.equals(sha256(input))) throw new IOException("NPC authentic frame hash mismatch");
				}
			}
		}
	}

	private static String archiveName(ByteBuffer input) throws IOException {
		StringBuilder out = new StringBuilder();
		while (input.hasRemaining()) {
			int value = input.get() & 0xff;
			if (value == 0) {
				String result = out.toString();
				if (!NAME.matcher(result).matches()) throw new IOException("NPC custom archive name is unsafe");
				return result;
			}
			if (value < 0x20 || value > 0x7e || out.length() >= 128) throw new IOException("NPC custom archive name is unsafe");
			out.append((char)value);
		}
		throw new IOException("NPC custom archive name is truncated");
	}
	private static byte[] read(InputStream input, long maximum) throws IOException {
		ByteArrayOutputStream output = new ByteArrayOutputStream(); byte[] buffer = new byte[8192]; long total = 0L;
		for (int count; (count = input.read(buffer)) >= 0;) {
			if (count == 0) continue; total += count;
			if (total > maximum) throw new IOException("NPC sprite content exceeds its bound");
			output.write(buffer, 0, count);
		}
		return output.toByteArray();
	}
	private static String sha256(InputStream input) throws IOException {
		try {
			MessageDigest digest = MessageDigest.getInstance("SHA-256");
			byte[] bytes = read(input, MAX_BYTES); digest.update(bytes);
			StringBuilder out = new StringBuilder();
			for (byte value : digest.digest()) out.append(String.format("%02x", value & 0xff));
			return out.toString();
		} catch (java.security.NoSuchAlgorithmException impossible) {
			throw new IllegalStateException(impossible);
		}
	}
	private static void requireKeys(JSONObject value, Set<String> keys) throws IOException {
		if (!value.keySet().equals(keys)) throw new IOException("NPC animation JSON contains unknown or missing keys");
	}
	private static String name(JSONObject value, String key) throws IOException {
		String result = text(value, key);
		if (!NAME.matcher(result).matches()) throw new IOException("NPC animation name is unsafe");
		return result;
	}
	private static String text(JSONObject value, String key) throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof String)) throw new IOException("NPC animation field is not text: " + key);
		return (String)raw;
	}
	private static boolean bool(JSONObject value, String key) throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof Boolean)) throw new IOException("NPC animation field is not boolean: " + key);
		return ((Boolean)raw).booleanValue();
	}
	private static int bounded(JSONObject value, String key, int low, int high) throws IOException {
		int result = integer(value, key);
		if (result < low || result > high) throw new IOException("NPC animation integer is outside its bound: " + key);
		return result;
	}
	private static int integer(JSONObject value, String key) throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof Number)) throw new IOException("NPC animation field is not integer: " + key);
		long result = ((Number)raw).longValue();
		if (raw instanceof Double || raw instanceof Float
			|| new BigDecimal(raw.toString()).compareTo(BigDecimal.valueOf(result)) != 0
			|| result < Integer.MIN_VALUE || result > Integer.MAX_VALUE) {
			throw new IOException("NPC animation field is not exact integer: " + key);
		}
		return (int)result;
	}
	private static Set<String> set(String... values) {
		return new HashSet<String>(Arrays.asList(values));
	}
}

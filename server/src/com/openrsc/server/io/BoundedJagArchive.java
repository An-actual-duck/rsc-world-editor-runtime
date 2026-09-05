package com.openrsc.server.io;

import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/** Strict, bounded r64 BZip2 JAG reader for offline migration, not a target loader. */
public final class BoundedJagArchive extends JContent {
    public static final int MAX_ARCHIVE_BYTES = 1048576;
    public static final int MAX_EXPANDED_BYTES = 16777216;
    public static final int MAX_ENTRY_BYTES = 65536;
    public static final int MAX_ENTRIES = 4096;
    private final Map<Integer, byte[]> entries = new LinkedHashMap<Integer, byte[]>();
    private final int expandedBytes;

    public BoundedJagArchive(byte[] source) throws IOException {
        if (source.length < 8 || source.length > MAX_ARCHIVE_BYTES)
            throw new IOException("JAG archive size is outside reviewed limits");
        int expanded = u24(source, 0), packed = u24(source, 3);
        if (packed != source.length - 6 || expanded < 2 || expanded > MAX_EXPANDED_BYTES)
            throw new IOException("JAG archive header lengths are invalid");
        byte[] data = unpackBytes(source, 6, packed, expanded);
        expandedBytes = data.length;
        int count = ((data[0] & 255) << 8) | (data[1] & 255);
        if (count > MAX_ENTRIES || 2L + count * 10L > data.length)
            throw new IOException("JAG entry table exceeds reviewed bounds");
        int offset = 2 + count * 10, total = 0;
        for (int index = 0; index < count; index++) {
            int table = 2 + index * 10;
            int hash = ((data[table] & 255) << 24) | ((data[table + 1] & 255) << 16)
                | ((data[table + 2] & 255) << 8) | (data[table + 3] & 255);
            int size = u24(data, table + 4), compressed = u24(data, table + 7);
            if (size > MAX_ENTRY_BYTES || (long) offset + compressed > data.length
                || (long) total + size > MAX_EXPANDED_BYTES || entries.containsKey(hash))
                throw new IOException("JAG entry is duplicated or exceeds reviewed bounds");
            entries.put(hash, unpackBytes(data, offset, compressed, size));
            offset += compressed; total += size;
        }
        if (offset != data.length) throw new IOException("JAG archive contains trailing bytes");
    }

    @Override public JContentFile unpack(String filename) {
        byte[] data = entries.get(nameHash(filename));
        return data == null ? null : new JContentFile(data);
    }

    public boolean contains(String filename) { return entries.containsKey(nameHash(filename)); }
    public int entryCount() { return entries.size(); }
    public int expandedBytes() { return expandedBytes; }

    private static int nameHash(String filename) {
        int hash = 0;
        for (char value : filename.toUpperCase(Locale.ROOT).toCharArray())
            hash = 61 * hash + value - 32;
        return hash;
    }

    private static int u24(byte[] data, int offset) {
        return ((data[offset] & 255) << 16) | ((data[offset + 1] & 255) << 8)
            | (data[offset + 2] & 255);
    }

    private static byte[] unpackBytes(byte[] source, int offset, int packed, int expanded)
        throws IOException {
        byte[] result = new byte[expanded];
        if (packed == expanded) {
            System.arraycopy(source, offset, result, 0, expanded);
            return result;
        }
        byte[] framed = new byte[packed + 4];
        framed[0] = 'B'; framed[1] = 'Z'; framed[2] = 'h'; framed[3] = '1';
        System.arraycopy(source, offset, framed, 4, packed);
        ByteArrayInputStream bytes = new ByteArrayInputStream(framed);
        try (BZip2CompressorInputStream input = new BZip2CompressorInputStream(bytes, false)) {
            int position = 0;
            while (position < result.length) {
                int count = input.read(result, position, result.length - position);
                if (count < 1) throw new IOException("JAG compressed stream is truncated");
                position += count;
            }
            if (input.read() != -1 || bytes.available() != 0)
                throw new IOException("JAG compressed stream has excess output or trailing data");
        } catch (RuntimeException malformed) {
            throw new IOException("JAG compressed stream is malformed", malformed);
        }
        return result;
    }
}

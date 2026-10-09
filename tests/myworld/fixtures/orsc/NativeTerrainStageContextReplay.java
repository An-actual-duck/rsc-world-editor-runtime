package orsc;

import com.openrsc.server.net.Packet;
import com.openrsc.server.net.rsc.NativeLayeredTerrainClientResidency;
import com.openrsc.server.net.rsc.NativeLayeredTerrainStageReadiness;
import com.openrsc.server.net.rsc.enums.OpcodeOut;
import com.openrsc.server.net.rsc.generators.impl.PayloadCustomGenerator;
import com.openrsc.server.net.rsc.struct.incoming.LayeredTerrainStageReadyStruct;
import com.openrsc.server.net.rsc.struct.outgoing.LayeredSceneContextStruct;
import com.openrsc.server.net.rsc.struct.outgoing.LayeredSceneTerrainChunkStruct;
import com.openrsc.server.net.rsc.struct.outgoing.LayeredTerrainStageStruct;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.Deflater;

/** The inserted sender/ACK methods are verbatim production source bodies. */
public final class NativeTerrainStageContextReplay {
    private static final int LAYERED_TERRAIN_STAGE_PROTOCOL_VERSION = 1;
    private static final int LAYERED_TERRAIN_SYMMETRIC_RESIDENCY_PROTOCOL_VERSION = 2;
    private static final int LAYERED_TERRAIN_SYMMETRIC_STRUCTURE_PROTOCOL_VERSION = 3;
    private static final int LAYERED_TERRAIN_PREDICTED_SYMMETRIC_PROTOCOL_VERSION = 4;
    private static final int LAYERED_TERRAIN_PREDICTED_SYMMETRIC_STRUCTURE_PROTOCOL_VERSION = 5;
    private static final int NATIVE_LAYERED_SYMMETRIC_RESIDENCY_RADIUS = 2;
    private static final String PACKAGE = "test.general-terrain";
    private static final String VERSION = "1.0.0";
    private static final String SHA = repeat('a');
    private static final String SOURCE_SHA = repeat('b');
    private static boolean wide;
    private final Object nativeTerrainWireCache = new Object();
    private final Player player = new Player();
    private final NativeLayeredTerrainClientResidency serverCache = new NativeLayeredTerrainClientResidency();
    private final NativeLayeredTerrainResidentCache clientCache = new NativeLayeredTerrainResidentCache();
    private final List<LayeredTerrainStageStruct> packets = new ArrayList<LayeredTerrainStageStruct>();
    private NativeLayeredTerrainSnapshot active;
    private int contextSequence;
    private int[] prediction = {3, 12};
    private boolean queueSucceeds = true;

    /* PRODUCTION_METHODS */

    private boolean nativeTerrainPredictionEnabled() { return true; }
    private boolean nativeTerrainSymmetricResidencyEnabled() { return true; }
    private int requireLayeredSceneContextSequence(Player ignored) { return contextSequence; }
    private int[] predictNativeTerrainCenter(Player ignored, NativeLayeredSceneTerrain terrain) { return prediction; }
    private FakeServer getServer() { return new FakeServer(); }
    private boolean tryFinalizeAndSendPacketChecked(OpcodeOut opcode, LayeredTerrainStageStruct stage, Player ignored) {
        require(opcode == OpcodeOut.SEND_LAYERED_TERRAIN_STAGE, "wrong opcode");
        if (!queueSucceeds) return false;
        packets.add(stage);
        return true;
    }

    private static final class FakeServer { int getCurrentTick() { return 42; } }
    private static final class Player {
        private final Map<String,Object> attributes = new HashMap<String,Object>();
        private boolean teleporting;
        @SuppressWarnings("unchecked")
        <T> T getAttribute(String key, T fallback) { return attributes.containsKey(key) ? (T)attributes.get(key) : fallback; }
        void setAttribute(String key, Object value) { attributes.put(key, value); }
        void removeAttribute(String key) { attributes.remove(key); }
        boolean isTeleporting() { return teleporting; }
        boolean isUsingCustomClient() { return true; }
    }
    private static final class WorldLocation {
        WorldLocation getWorldSpace() { return this; }
        WorldLocation getCoordinate() { return this; }
        String getValue() { return "global"; }
        int getLevel() { return 0; }
    }
    private static final class TerrainPackage { String getManifestSha256() { return SHA; } }

    /** Synthetic immutable terrain input, with production encoding/identity shapes. */
    private static final class NativeLayeredSceneTerrain {
        final NativeLayeredTerrainClientResidency residency;
        final TerrainPackage terrainPackage;
        final int currentChunkX;
        final int currentChunkY;
        NativeLayeredTerrainClientResidency.Transaction transaction;
        NativeLayeredSceneTerrain(Object server, Object wire, NativeLayeredTerrainClientResidency cache,
                                 TerrainPackage terrain, WorldLocation location, int x, int y) {
            residency = cache; terrainPackage = terrain; currentChunkX = x; currentChunkY = y;
        }
        void populate(LayeredTerrainStageStruct stage) { populate(stage, 1); }
        void populate(LayeredTerrainStageStruct stage, int radius) { fill(stage, radius, false); }
        void populateSymmetricStructure(LayeredTerrainStageStruct stage) { fill(stage, 2, true); }
        void fill(LayeredTerrainStageStruct stage, int radius, boolean structural) {
            stage.nativePackageId = PACKAGE; stage.nativePackageVersion = VERSION;
            stage.nativeManifestSha256 = SHA; stage.nativePresentationChunkSize = 48;
            stage.nativeCurrentChunkX = currentChunkX; stage.nativeCurrentChunkY = currentChunkY;
            stage.nativeChunkRadius = radius;
            transaction = residency.begin();
            populateChunks(stage.nativeChunks, transaction, currentChunkX, currentChunkY, radius, structural);
        }
        void commitResidency() { if (transaction != null) { transaction.commit(); transaction = null; } }
    }

    private NativeLayeredSceneTerrain terrain(int x, int y) {
        return new NativeLayeredSceneTerrain(getServer(), nativeTerrainWireCache, serverCache,
                                            new TerrainPackage(), new WorldLocation(), x, y);
    }

    private static void populateChunks(List<LayeredSceneTerrainChunkStruct> chunks,
            NativeLayeredTerrainClientResidency.Transaction transaction, int x, int y,
            int radius, boolean structural) {
        for (int dx = -radius; dx <= radius; dx++) for (int dy = -radius; dy <= radius; dy++) {
            LayeredSceneTerrainChunkStruct slot = new LayeredSceneTerrainChunkStruct();
            slot.chunkX = slot.sourceSectorX = x + dx; slot.chunkY = slot.sourceSectorY = y + dy;
            boolean outer = Math.max(Math.abs(dx), Math.abs(dy)) == 2;
            slot.available = !structural || outer;
            if (slot.available) {
                slot.sourceEncoding = structural
                    ? (wide ? NativeLayeredTerrainChunk.STRUCTURAL_ENCODING_V2 : NativeLayeredTerrainChunk.STRUCTURAL_ENCODING)
                    : outer ? (wide ? NativeLayeredTerrainChunk.VISUAL_ENCODING_V2 : NativeLayeredTerrainChunk.VISUAL_ENCODING)
                    : (wide ? NativeLayeredTerrainChunk.RAW_ENCODING_V2 : NativeLayeredTerrainChunk.RAW_ENCODING);
                slot.sourcePayloadSha256 = SOURCE_SHA;
                slot.payloadPresent = transaction.requiresPayload(identity(slot));
                if (slot.payloadPresent) {
                    int width = structural ? 7 : outer ? (wide ? 4 : 3) : (wide ? 11 : 10);
                    slot.tileBytes = compress(new byte[48 * 48 * width]);
                }
            }
            chunks.add(slot);
        }
    }
    private static String identity(LayeredSceneTerrainChunkStruct slot) {
        return PACKAGE + "@" + VERSION + ":" + SHA + ":global:0:48:"
            + slot.chunkX + "," + slot.chunkY + ":" + slot.sourceSectorX + "," + slot.sourceSectorY
            + ":" + slot.sourceEncoding + ":" + SOURCE_SHA;
    }

    private void context(int x, int y) {
        LayeredSceneContextStruct context = new LayeredSceneContextStruct();
        context.protocolVersion = 8; context.sequence = ++contextSequence; context.serverTick = 42;
        context.worldSpace = "global"; context.projectionId = "native-layered-package-v1";
        context.logicalX = context.legacyX = x * 48; context.logicalY = context.legacyY = y * 48;
        context.logicalLevel = 0; context.nativePackageId = PACKAGE; context.nativePackageVersion = VERSION;
        context.nativeManifestSha256 = SHA; context.nativePresentationChunkSize = 48;
        context.nativeCurrentChunkX = x; context.nativeCurrentChunkY = y; context.nativeChunkRadius = 1;
        NativeLayeredTerrainClientResidency.Transaction transaction = serverCache.begin();
        populateChunks(context.nativeChunks, transaction, x, y, 1, false);
        context.setOpcode(OpcodeOut.SEND_LAYERED_SCENE_CONTEXT);
        Packet packet = new PayloadCustomGenerator().generate(context, null);
        transaction.commit(); // Matches production checked context queue's successful path.
        clearNativeTerrainStage(player);
        byte[] bytes = readPacket(packet);
        int bodyStart = 1 + 4 + 4 + "global".length() + 1
            + context.projectionId.length() + 1 + 4 * 3 + 2 * 2;
        active = NativeLayeredTerrainPacketDecoder.decodeV8(Arrays.copyOfRange(bytes, bodyStart, bytes.length),
                                                           "global", 0, clientCache);
        assertPaired("context " + contextSequence);
    }

    private LayeredTerrainStageStruct lastPacket() { return packets.get(packets.size() - 1); }
    private void decode(LayeredTerrainStageStruct stage) {
        stage.setOpcode(OpcodeOut.SEND_LAYERED_TERRAIN_STAGE);
        byte[] bytes = readPacket(new PayloadCustomGenerator().generate(stage, null));
        int bodyStart = 1 + 4 * 3 + "global".length() + 1 + 4;
        byte[] body = Arrays.copyOfRange(bytes, bodyStart, bytes.length);
        if (stage.protocolVersion == 1) NativeLayeredTerrainPacketDecoder.decodeV7Stage(body, "global", 0, clientCache, active);
        else if (stage.protocolVersion == 2) NativeLayeredTerrainPacketDecoder.decodeV9Halo(body, "global", 0, clientCache, active);
        else if (stage.protocolVersion == 3) NativeLayeredTerrainPacketDecoder.decodeV10Structure(body, "global", 0, clientCache, active);
        else if (stage.protocolVersion == 4) NativeLayeredTerrainPacketDecoder.decodePredictedSymmetricHalo(body, "global", 0, clientCache, active);
        else NativeLayeredTerrainPacketDecoder.decodePredictedSymmetricStructure(body, "global", 0, clientCache, active);
        assertPaired("stage " + stage.sequence + " BEFORE ACK");
    }

    private void ack(LayeredTerrainStageStruct stage) {
        LayeredTerrainStageReadyStruct ready = new LayeredTerrainStageReadyStruct();
        ready.protocolVersion = stage.protocolVersion; ready.stageSequence = stage.sequence;
        ready.contextSequence = stage.contextSequence; ready.worldSpace = stage.worldSpace;
        ready.logicalLevel = stage.logicalLevel; ready.centerSectorX = stage.nativeCurrentChunkX;
        ready.centerSectorY = stage.nativeCurrentChunkY; ready.manifestSha256 = stage.nativeManifestSha256;
        acceptLayeredTerrainStageReady(player, ready);
        assertPaired("ACK " + stage.sequence);
    }
    private void haloThenStructure(int x, int y) {
        maybeSendNativeTerrainSymmetricResidency(player, new WorldLocation(), terrain(x, y));
        LayeredTerrainStageStruct visual = lastPacket(); decode(visual); ack(visual);
        maybeSendNativeTerrainSymmetricResidency(player, new WorldLocation(), terrain(x, y));
        LayeredTerrainStageStruct structural = lastPacket(); decode(structural); ack(structural);
    }
    @SuppressWarnings("unchecked")
    private static List<String> keys(Object cache) {
        try {
            Field field = cache.getClass().getDeclaredField("resident"); field.setAccessible(true);
            return new ArrayList<String>(((LinkedHashMap<String,?>)field.get(cache)).keySet());
        } catch (ReflectiveOperationException failure) { throw new AssertionError(failure); }
    }
    private void assertPaired(String phase) {
        List<String> server = keys(serverCache), client = keys(clientCache);
        require(server.equals(client), "wire residency mismatch " + phase + ": server=" + server.size()
            + " client=" + client.size() + " ordered identities differ");
    }

    public static void main(String[] args) {
        wide = args.length > 0 && "wide".equals(args[0]);
        NativeTerrainStageContextReplay replay = new NativeTerrainStageContextReplay();
        replay.context(3, 13);
        replay.haloThenStructure(3, 13);
        replay.sendNativeTerrainPredictedSymmetricStage(replay.player, new WorldLocation(), replay.terrain(3, 12), false);
        LayeredTerrainStageStruct pendingVisual = replay.lastPacket(); replay.decode(pendingVisual);
        // A direction reversal picks a different center while prediction's ACK is delayed.
        require(replay.canActivateNativeTerrainStage(replay.player, new WorldLocation(), replay.terrain(2, 13)),
                "different center should not wait for unused prebuild");
        replay.context(2, 13);
        replay.ack(pendingVisual); replay.ack(pendingVisual); // Late and duplicate are inert.
        replay.haloThenStructure(2, 13);
        // Exact target readiness is still required; wire residency is not readiness.
        replay.sendNativeTerrainPredictedSymmetricStage(replay.player, new WorldLocation(), replay.terrain(2, 12), false);
        LayeredTerrainStageStruct visual = replay.lastPacket(); replay.decode(visual);
        require(!replay.canActivateNativeTerrainStage(replay.player, new WorldLocation(), replay.terrain(2, 12)),
                "unacknowledged prediction activated");
        replay.ack(visual);
        require(!replay.canActivateNativeTerrainStage(replay.player, new WorldLocation(), replay.terrain(2, 12)),
                "visual-only prediction activated before structure");
        replay.sendNativeTerrainPredictedSymmetricStage(replay.player, new WorldLocation(), replay.terrain(2, 12), true);
        LayeredTerrainStageStruct structural = replay.lastPacket(); replay.decode(structural);
        require(!replay.canActivateNativeTerrainStage(replay.player, new WorldLocation(), replay.terrain(2, 12)),
                "unacknowledged structure activated");
        replay.ack(visual); // Older valid ACK must not publish readiness of the newer stage.
        require(!replay.canActivateNativeTerrainStage(replay.player, new WorldLocation(), replay.terrain(2, 12)), "stale ACK activated structure");
        replay.ack(structural); replay.ack(structural);
        require(replay.canActivateNativeTerrainStage(replay.player, new WorldLocation(), replay.terrain(2, 12)), "exact ACK did not activate");
        replay.context(2, 12);
        replay.haloThenStructure(2, 12);
        require(replay.serverCache.size() == 64, "fixture did not pressure full LRU");
        // Reversals across capacity must agree despite full/visual/structural identities.
        for (int i = 0; i < 8; i++) {
            int x = i % 2 == 0 ? 3 : 2, y = i % 2 == 0 ? 13 : 12;
            replay.sendNativeTerrainPredictedSymmetricStage(replay.player, new WorldLocation(), replay.terrain(x, y), false);
            LayeredTerrainStageStruct cancelled = replay.lastPacket(); replay.decode(cancelled);
            replay.context(i % 2 == 0 ? 2 : 3, i % 2 == 0 ? 13 : 12);
            replay.ack(cancelled);
            replay.haloThenStructure(i % 2 == 0 ? 2 : 3, i % 2 == 0 ? 13 : 12);
        }
        // Existing v7 stage sender uses the same queue boundary.
        replay.prediction = new int[]{replay.active.getCurrentChunkX() + 1, replay.active.getCurrentChunkY()};
        replay.maybeSendNativeTerrainStage(replay.player, new WorldLocation(), replay.terrain(replay.active.getCurrentChunkX(), replay.active.getCurrentChunkY()));
        LayeredTerrainStageStruct v7 = replay.lastPacket(); replay.decode(v7);
        replay.player.teleporting = true;
        replay.context(20, 20); // Teleport cancels readiness, not already delivered cache effects.
        replay.ack(v7); replay.ack(v7); replay.player.teleporting = false;
        List<String> before = keys(replay.serverCache);
        replay.queueSucceeds = false;
        replay.sendNativeTerrainPredictedSymmetricStage(replay.player, new WorldLocation(), replay.terrain(21, 20), false);
        replay.maybeSendNativeTerrainStage(replay.player, new WorldLocation(), replay.terrain(20, 20));
        replay.maybeSendNativeTerrainSymmetricResidency(replay.player, new WorldLocation(), replay.terrain(20, 20));
        require(before.equals(keys(replay.serverCache)), "failed queue changed mirror");
        require(replay.player.getAttribute(NATIVE_TERRAIN_PENDING_STAGE_ATTRIBUTE, null) == null, "failed queue published pending");
        replay.assertPaired("failed queue");
        replay.queueSucceeds = true;
        replay.serverCache.clear(); replay.clientCache.clear(); clearNativeTerrainStage(replay.player);
        replay.context(3, 13); replay.haloThenStructure(3, 13);
        replay.ack(structural); replay.assertPaired("reconnect and ancient ACK");
        System.out.println((wide ? "wide: " : "legacy: ") + "PASS: production stage queue/ACK replay, full paired wire/decoder cache order, capacity, reversal, teleport, reconnect, failed queues");
    }
    private static byte[] readPacket(Packet packet) {
        try { return packet.readBytes(packet.getBuffer().readableBytes()); }
        finally { packet.getBuffer().release(); }
    }
    private static byte[] compress(byte[] raw) {
        Deflater deflater = new Deflater(Deflater.BEST_SPEED);
        try {
            deflater.setInput(raw); deflater.finish(); byte[] wire = new byte[raw.length + 128];
            int length = deflater.deflate(wire); require(deflater.finished(), "compression failed");
            return Arrays.copyOf(wire, length);
        } finally { deflater.end(); }
    }
    private static String repeat(char c) { char[] bytes = new char[64]; Arrays.fill(bytes, c); return new String(bytes); }
    private static void require(boolean condition, String label) { if (!condition) throw new AssertionError(label); }
}

#!/usr/bin/env python3
"""Regression coverage for custom-client framing before authentication."""

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"


HARNESS = r"""
import com.openrsc.server.net.ConnectionAttachment;
import com.openrsc.server.net.Packet;
import com.openrsc.server.net.RSCProtocolDecoder;
import com.openrsc.server.net.rsc.ISAACContainer;
import com.openrsc.server.login.ISAACCipher;
import io.netty.buffer.Unpooled;
import io.netty.channel.embedded.EmbeddedChannel;

public final class CustomLoginDecoderHarness {
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static byte[] frame(int length, int opcode) {
        byte[] result = new byte[length + 2];
        result[0] = (byte) (length >>> 8);
        result[1] = (byte) length;
        result[2] = (byte) opcode;
        for (int index = 3; index < result.length; index++) {
            result[index] = (byte) (index & 255);
        }
        return result;
    }

    private static EmbeddedChannel channel(ConnectionAttachment attachment) {
        EmbeddedChannel result = new EmbeddedChannel(new RSCProtocolDecoder());
        result.attr(RSCProtocolDecoder.attachment).set(attachment);
        return result;
    }

    private static void requirePacket(
        EmbeddedChannel channel, int opcode, int length, String label) {
        Packet packet = channel.readInbound();
        require(packet != null, label + " did not deliver a packet");
        require(packet.getID() == opcode, label + " opcode");
        require(packet.getLength() == length, label + " payload length");
    }

    private static void fragmentedAtEveryBoundary(int length) {
        byte[] login = frame(length, 0);
        for (int cut = 1; cut < login.length; cut++) {
            ConnectionAttachment attachment = new ConnectionAttachment();
            EmbeddedChannel channel = channel(attachment);
            channel.writeInbound(Unpooled.wrappedBuffer(login, 0, cut));
            require(channel.readInbound() == null,
                length + " login delivered at fragment boundary " + cut);
            require(attachment.authenticClient.get() == null,
                length + " login classified at fragment boundary " + cut);
            channel.writeInbound(Unpooled.wrappedBuffer(login, cut, login.length - cut));
            require(Short.valueOf((short) -1).equals(attachment.authenticClient.get()),
                length + " login did not select custom framing at boundary " + cut);
            requirePacket(channel, 0, length - 1,
                length + " login at fragment boundary " + cut);
            require(channel.readInbound() == null,
                length + " login delivered twice at boundary " + cut);
            channel.finishAndReleaseAll();
        }
    }

    private static void boundaryAndOrdinaryLogins() {
        for (int length : new int[] {80, 255, 256, 278}) {
            ConnectionAttachment attachment = new ConnectionAttachment();
            EmbeddedChannel channel = channel(attachment);
            channel.writeInbound(Unpooled.wrappedBuffer(frame(length, 0)));
            require(Short.valueOf((short) -1).equals(attachment.authenticClient.get()),
                "login length " + length + " did not classify custom");
            requirePacket(channel, 0, length - 1, "login length " + length);
            require(channel.readInbound() == null, "login length " + length + " duplicate");
            channel.finishAndReleaseAll();
        }
    }

    private static void coalescedFramesAreDeliveredOnce() {
        ConnectionAttachment attachment = new ConnectionAttachment();
        EmbeddedChannel channel = channel(attachment);
        byte[][] frames = new byte[][] {frame(278, 0), frame(1, 19), frame(5, 42)};
        byte[] joined = new byte[frames[0].length + frames[1].length + frames[2].length];
        int offset = 0;
        for (byte[] value : frames) {
            System.arraycopy(value, 0, joined, offset, value.length);
            offset += value.length;
        }
        channel.writeInbound(Unpooled.wrappedBuffer(joined));
        requirePacket(channel, 0, 277, "coalesced login");
        requirePacket(channel, 19, 0, "coalesced initial-config request");
        requirePacket(channel, 42, 4, "coalesced ordinary custom packet");
        require(channel.readInbound() == null, "coalesced frames delivered more than once");
        channel.finishAndReleaseAll();
    }

    private static void initialConfigAndLegacyTrafficRemainDistinct() {
        ConnectionAttachment custom = new ConnectionAttachment();
        EmbeddedChannel customChannel = channel(custom);
        customChannel.writeInbound(Unpooled.wrappedBuffer(frame(1, 19)));
        require(Short.valueOf((short) -1).equals(custom.authenticClient.get()),
            "initial-config request did not select custom framing");
        requirePacket(customChannel, 19, 0, "initial-config request");
        require(customChannel.readInbound() == null, "initial-config duplicate");
        customChannel.finishAndReleaseAll();

        ConnectionAttachment legacy = new ConnectionAttachment();
        EmbeddedChannel legacyChannel = channel(legacy);
        legacyChannel.writeInbound(Unpooled.wrappedBuffer(new byte[] {1, 19, 2}));
        requirePacket(legacyChannel, 19, 1, "authentic legacy configuration request");
        require(legacy.authenticClient.get() == null, "legacy request became custom");
        legacyChannel.finishAndReleaseAll();

        ConnectionAttachment session = new ConnectionAttachment();
        EmbeddedChannel sessionChannel = channel(session);
        sessionChannel.writeInbound(Unpooled.wrappedBuffer(new byte[] {2, 10, 32}));
        requirePacket(sessionChannel, 32, 2, "authentic session-ID request");
        require(session.authenticClient.get() == null, "session-ID request became custom");
        sessionChannel.finishAndReleaseAll();

        ConnectionAttachment longLegacy = new ConnectionAttachment();
        EmbeddedChannel longLegacyChannel = channel(longLegacy);
        byte[] longFrame = new byte[202];
        longFrame[0] = (byte) 160;
        longFrame[1] = (byte) 200;
        longFrame[2] = (byte) 42;
        longLegacyChannel.writeInbound(Unpooled.wrappedBuffer(longFrame));
        requirePacket(longLegacyChannel, 42, 199, "two-byte authentic legacy frame");
        require(longLegacy.authenticClient.get() == null,
            "two-byte authentic legacy frame became custom");
        longLegacyChannel.finishAndReleaseAll();

        ConnectionAttachment isaac = new ConnectionAttachment();
        isaac.authenticClient.set((short) 183);
        int[] keys = new int[] {11, 22, 33, 44};
        ISAACCipher incoming = new ISAACCipher();
        incoming.setKeys(keys);
        ISAACCipher outgoing = new ISAACCipher();
        outgoing.setKeys(keys);
        ISAACCipher encoder = new ISAACCipher();
        encoder.setKeys(keys);
        isaac.ISAAC.set(new ISAACContainer(incoming, outgoing));
        EmbeddedChannel isaacChannel = channel(isaac);
        byte[] isaacFrame = new byte[202];
        isaacFrame[0] = (byte) 160;
        isaacFrame[1] = (byte) 200;
        isaacFrame[2] = (byte) ((42 + encoder.getNextValue()) & 255);
        isaacChannel.writeInbound(Unpooled.wrappedBuffer(isaacFrame));
        requirePacket(isaacChannel, 42, 199, "preclassified ISAAC frame");
        isaacChannel.finishAndReleaseAll();
    }

    private static void expectFailure(byte[] value, boolean close, String label) {
        ConnectionAttachment attachment = new ConnectionAttachment();
        EmbeddedChannel channel = channel(attachment);
        boolean failed = false;
        try {
            channel.writeInbound(Unpooled.wrappedBuffer(value));
            if (close) channel.finish();
        } catch (RuntimeException expected) {
            failed = true;
        } finally {
            channel.close();
        }
        require(failed, label + " did not fail closed");
        require(channel.readInbound() == null, label + " delivered a packet");
        require(attachment.authenticClient.get() == null, label + " classified a client");
    }

    private static void malformedAndTruncatedFramesFailClosed() {
        expectFailure(new byte[] {0, 0, 0}, false, "zero length");
        expectFailure(new byte[] {0, 38, 0}, false, "short login");
        expectFailure(new byte[] {32, 1, 0}, false, "excessive login");
        byte[] truncated = new byte[13];
        truncated[0] = 1;
        truncated[1] = 22;
        truncated[2] = 0;
        expectFailure(truncated, true, "truncated 278-byte login");
    }

    public static void main(String[] args) {
        fragmentedAtEveryBoundary(255);
        fragmentedAtEveryBoundary(256);
        fragmentedAtEveryBoundary(278);
        boundaryAndOrdinaryLogins();
        coalescedFramesAreDeliveredOnce();
        initialConfigAndLegacyTrafficRemainDistinct();
        malformedAndTruncatedFramesFailClosed();
        System.out.println("custom-login-decoder-ok");
    }
}
"""


class CustomLoginDecoderTest(unittest.TestCase):
    def test_real_decoder_framing_boundaries_and_failures(self):
        self.assertTrue(CORE.is_file(), "run ./scripts/build-server.sh first")
        with tempfile.TemporaryDirectory(prefix="custom-login-decoder-") as temp:
            root = Path(temp)
            source = root / "CustomLoginDecoderHarness.java"
            source.write_text(textwrap.dedent(HARNESS), encoding="utf-8")
            subprocess.run(
                ["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
                 "-d", str(root), str(source)],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            result = subprocess.run(
                ["java", "-cp", str(CORE) + ":" + str(root),
                 "CustomLoginDecoderHarness"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue(
                result.stdout.endswith("custom-login-decoder-ok\n"), result.stdout
            )


if __name__ == "__main__":
    unittest.main()

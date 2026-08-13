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

import java.nio.charset.StandardCharsets;

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

    private static byte[] customLoginFrame(int length, int opcode, boolean reconnecting) {
        require(length >= 27, "custom login fixture length");
        byte[] result = new byte[length + 2];
        result[0] = (byte) (length >>> 8);
        result[1] = (byte) length;
        result[2] = (byte) opcode;
        result[3] = (byte) (reconnecting ? 1 : 0);
        result[4] = 0;
        result[5] = 0;
        result[6] = 39;
        result[7] = 64; // client version 10048
        int cursor = 8;
        byte[] username = "Builder".getBytes(StandardCharsets.US_ASCII);
        System.arraycopy(username, 0, result, cursor, username.length);
        cursor += username.length;
        result[cursor++] = 10;
        result[cursor++] = 0; // structurally valid unencrypted password
        byte[] password = "test".getBytes(StandardCharsets.US_ASCII);
        System.arraycopy(password, 0, result, cursor, password.length);
        cursor += password.length;
        result[cursor++] = 10;
        cursor += 8; // UID
        require(cursor <= result.length, "custom login fixture payload");
        return result;
    }

    private static byte[] registrationFrame(boolean withEmail) {
        byte[] username = "Builder             ".getBytes(StandardCharsets.US_ASCII);
        byte[] password = "password            ".getBytes(StandardCharsets.US_ASCII);
        byte[] email = "builder@example.test".getBytes(StandardCharsets.US_ASCII);
        int length = 1 + username.length + 1 + password.length + 1
            + (withEmail ? email.length + 1 : 0);
        byte[] result = new byte[length + 2];
        result[0] = (byte) (length >>> 8);
        result[1] = (byte) length;
        result[2] = 2;
        int cursor = 3;
        byte[][] fields = withEmail
            ? new byte[][] {username, password, email}
            : new byte[][] {username, password};
        for (byte[] field : fields) {
            System.arraycopy(field, 0, result, cursor, field.length);
            cursor += field.length;
            result[cursor++] = 10;
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

    private static void fragmentedAtEveryBoundary(byte[] value, int opcode, String label) {
        for (int cut = 1; cut < value.length; cut++) {
            ConnectionAttachment attachment = new ConnectionAttachment();
            EmbeddedChannel channel = channel(attachment);
            channel.writeInbound(Unpooled.wrappedBuffer(value, 0, cut));
            require(channel.readInbound() == null,
                label + " delivered at fragment boundary " + cut);
            require(attachment.authenticClient.get() == null,
                label + " classified at fragment boundary " + cut);
            channel.writeInbound(Unpooled.wrappedBuffer(value, cut, value.length - cut));
            require(Short.valueOf((short) -1).equals(attachment.authenticClient.get()),
                label + " did not select custom framing at boundary " + cut);
            requirePacket(channel, opcode, value.length - 3,
                label + " at fragment boundary " + cut);
            require(channel.readInbound() == null,
                label + " delivered twice at boundary " + cut);
            channel.finishAndReleaseAll();
        }
    }

    private static void boundaryAndOrdinaryLogins() {
        for (int length : new int[] {80, 255, 256, 278}) {
            ConnectionAttachment attachment = new ConnectionAttachment();
            EmbeddedChannel channel = channel(attachment);
            channel.writeInbound(Unpooled.wrappedBuffer(
                customLoginFrame(length, 0, false)));
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
        byte[][] frames = new byte[][] {
            customLoginFrame(278, 0, false),
            frame(1, 19),
            customLoginFrame(80, 19, true),
            registrationFrame(true),
            frame(5, 42)
        };
        int joinedLength = 0;
        for (byte[] value : frames) joinedLength += value.length;
        byte[] joined = new byte[joinedLength];
        int offset = 0;
        for (byte[] value : frames) {
            System.arraycopy(value, 0, joined, offset, value.length);
            offset += value.length;
        }
        channel.writeInbound(Unpooled.wrappedBuffer(joined));
        requirePacket(channel, 0, 277, "coalesced login");
        requirePacket(channel, 19, 0, "coalesced initial-config request");
        requirePacket(channel, 19, 79, "coalesced relogin");
        requirePacket(channel, 2, registrationFrame(true).length - 3,
            "coalesced registration");
        requirePacket(channel, 42, 4, "coalesced ordinary custom packet");
        require(channel.readInbound() == null, "coalesced frames delivered more than once");
        channel.finishAndReleaseAll();
    }

    private static void coalescedUndecidedFrameIsDeliveredOnce(
        byte[] first, int opcode, String label) {
        byte[] ordinary = frame(5, 42);
        byte[] joined = new byte[first.length + ordinary.length];
        System.arraycopy(first, 0, joined, 0, first.length);
        System.arraycopy(ordinary, 0, joined, first.length, ordinary.length);
        ConnectionAttachment attachment = new ConnectionAttachment();
        EmbeddedChannel channel = channel(attachment);
        channel.writeInbound(Unpooled.wrappedBuffer(joined));
        require(Short.valueOf((short) -1).equals(attachment.authenticClient.get()),
            label + " did not select custom framing");
        requirePacket(channel, opcode, first.length - 3, label);
        requirePacket(channel, 42, 4, label + " following packet");
        require(channel.readInbound() == null, label + " delivered more than once");
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
        byte[] legacyCollision = new byte[] {1, 19, 2, 1, 42};
        legacyChannel.writeInbound(Unpooled.wrappedBuffer(legacyCollision));
        requirePacket(legacyChannel, 19, 1, "authentic legacy configuration request");
        requirePacket(legacyChannel, 42, 2,
            "packet following authentic legacy configuration request");
        require(legacyChannel.readInbound() == null,
            "legacy registration collision left decoded packets");
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

        ConnectionAttachment loginCollision = new ConnectionAttachment();
        EmbeddedChannel loginCollisionChannel = channel(loginCollision);
        byte[] coincidentalLogin = new byte[] {8, 22, 0, 7, 1, 2, 3, 4, 5};
        loginCollisionChannel.writeInbound(Unpooled.wrappedBuffer(coincidentalLogin));
        requirePacket(loginCollisionChannel, 0, 8,
            "legacy length/opcode collision");
        require(loginCollisionChannel.readInbound() == null,
            "legacy login collision left decoded packets");
        require(loginCollision.authenticClient.get() == null,
            "legacy length/opcode collision became custom");
        loginCollisionChannel.finishAndReleaseAll();

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
        byte[] shortLogin = new byte[19];
        shortLogin[0] = 0;
        shortLogin[1] = 17;
        shortLogin[2] = 0;
        shortLogin[6] = 39;
        shortLogin[7] = 64;
        expectFailure(shortLogin, false, "short login");
        expectFailure(new byte[] {32, 1, 0}, false, "excessive login");
        byte[] malformedLogin = customLoginFrame(80, 0, false);
        malformedLogin[16] = 3;
        expectFailure(malformedLogin, false, "unsupported login encryption");
		byte[] malformedRelogin = customLoginFrame(80, 19, true);
		malformedRelogin[16] = 3;
		expectFailure(malformedRelogin, false, "unsupported relogin encryption");

        byte[] malformedRegistration = registrationFrame(true);
        malformedRegistration[malformedRegistration.length - 1] = 'x';
        expectFailure(malformedRegistration, false, "malformed registration");
		byte[] malformedRegistrationWithoutEmail = registrationFrame(false);
		malformedRegistrationWithoutEmail[malformedRegistrationWithoutEmail.length - 1] = 'x';
		expectFailure(malformedRegistrationWithoutEmail, false,
			"malformed registration without email");
		expectFailure(new byte[] {32, 1, 19}, false, "excessive relogin");
		expectFailure(new byte[] {32, 1, 2}, false, "excessive registration");

        for (byte[] truncated : new byte[][] {
                customLoginFrame(278, 0, false),
                customLoginFrame(80, 19, true),
                registrationFrame(true),
				registrationFrame(false)}) {
            byte[] prefix = new byte[24];
            System.arraycopy(truncated, 0, prefix, 0, prefix.length);
            expectFailure(prefix, true, "truncated opcode " + (truncated[2] & 255));
        }
    }

    private static void loginEncryptionVersionTwoRemainsAccepted() {
		for (int opcode : new int[] {0, 19}) {
			byte[] value = customLoginFrame(80, opcode, opcode == 19);
			value[16] = 2;
			ConnectionAttachment attachment = new ConnectionAttachment();
			EmbeddedChannel channel = channel(attachment);
			channel.writeInbound(Unpooled.wrappedBuffer(value));
			require(Short.valueOf((short) -1).equals(attachment.authenticClient.get()),
				"encryption version 2 opcode " + opcode + " did not classify custom");
			requirePacket(channel, opcode, 79,
				"encryption version 2 opcode " + opcode);
			require(channel.readInbound() == null,
				"encryption version 2 opcode " + opcode + " duplicate");
			channel.finishAndReleaseAll();
		}
	}

    public static void main(String[] args) {
        fragmentedAtEveryBoundary(customLoginFrame(255, 0, false), 0, "255 login");
        fragmentedAtEveryBoundary(customLoginFrame(256, 0, false), 0, "256 login");
        fragmentedAtEveryBoundary(customLoginFrame(278, 0, false), 0, "278 login");
        fragmentedAtEveryBoundary(customLoginFrame(80, 19, true), 19, "relogin");
        fragmentedAtEveryBoundary(
			registrationFrame(false), 2, "registration without email");
		fragmentedAtEveryBoundary(
			registrationFrame(true), 2, "registration with email");
        boundaryAndOrdinaryLogins();
		loginEncryptionVersionTwoRemainsAccepted();
        coalescedFramesAreDeliveredOnce();
		coalescedUndecidedFrameIsDeliveredOnce(
			customLoginFrame(80, 19, true), 19, "coalesced undecided relogin");
		coalescedUndecidedFrameIsDeliveredOnce(
			registrationFrame(false), 2,
			"coalesced undecided registration without email");
		coalescedUndecidedFrameIsDeliveredOnce(
			registrationFrame(true), 2,
			"coalesced undecided registration with email");
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

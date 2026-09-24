#!/usr/bin/env python3
"""Exercise material identity, texture references, and cache invalidation."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLIENT_JAR = ROOT / "Client_Base/Open_RSC_Client.jar"
FRAME_SOURCE = ROOT / "Client_Base/src/orsc/graphics/three/Renderer3DFrame.java"
WORLD_FRAME_SOURCE = (
    ROOT / "Client_Base/src/orsc/graphics/three/Renderer3DWorldChunkFrame.java"
)
TEXTURE_CACHE_SOURCE = ROOT / "PC_Client/src/orsc/OpenGLWorldTextureCache.java"

FIXTURE = r"""
package orsc;

import orsc.graphics.three.Renderer3DFrame;
import orsc.graphics.three.Renderer3DModelKind;
import orsc.graphics.three.Renderer3DTextureData;
import orsc.graphics.three.Renderer3DWorldChunkFrame;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Arrays;

public final class OpenGLWorldTextureReferenceFixture {
	private static final int LEGACY_TRANSPARENT_TEXTURE = 12345678;

	private OpenGLWorldTextureReferenceFixture() {
	}

	public static void main(String[] args) throws Exception {
		Renderer3DTextureData texture0 = texture(0, 0x224466);
		Renderer3DTextureData texture1 = texture(1, 0x446688);
		Renderer3DTextureData texture2 = texture(2, 0x6688aa);
		Renderer3DTextureData texture3 = texture(3, 0x88aacc);
		Renderer3DTextureData texture3Changed = texture(3, 0xaaccff);

		Renderer3DTextureData[] sourceCatalog = new Renderer3DTextureData[] {
			texture0,
			texture1,
			texture2,
			texture3,
		};
		Renderer3DFrame frame = frame(sourceCatalog);
		sourceCatalog[0] = texture3Changed;
		assertSame(texture0, frame.getTexture(0), "frame snapshots source catalog");
		assertEquals(4, frame.getTextureCount(), "texture catalog count");

		Renderer3DFrame sameCatalog = frame(new Renderer3DTextureData[] {
			texture0,
			texture1,
			texture2,
			texture3,
		});
		Renderer3DFrame changedUnreferencedTexture = frame(new Renderer3DTextureData[] {
			texture0,
			texture1,
			texture2,
			texture3Changed,
		});
		assertEquals(
			frame.getTextureCatalogSignature(),
			sameCatalog.getTextureCatalogSignature(),
			"stable catalog signature");
		assertNotEquals(
			frame.getTextureCatalogSignature(),
			changedUnreferencedTexture.getTextureCatalogSignature(),
			"catalog signature invalidates conservatively");

		Renderer3DWorldChunkFrame.ChunkMesh first = chunk(
			new int[] {0, 1, LEGACY_TRANSPARENT_TEXTURE, 1, -1},
			new int[] {0, 0, 2, 0, 0},
			101L);
		Renderer3DWorldChunkFrame.ChunkMesh second = chunk(
			new int[] {2, 0, 2},
			new int[] {0, 0, 0},
			202L);
		assertReferences(
			first,
			new int[] {0, 1, LEGACY_TRANSPARENT_TEXTURE},
			"chunk references exclude RGB fallback");

		Renderer3DWorldChunkFrame world = Renderer3DWorldChunkFrame.fromChunks(
			Arrays.asList(first, second));
		assertReferences(
			world,
			new int[] {0, 1, 2, LEGACY_TRANSPARENT_TEXTURE},
			"frame references");
		Renderer3DWorldChunkFrame sameWorld = Renderer3DWorldChunkFrame.fromChunks(
			Arrays.asList(first, second));
		Renderer3DWorldChunkFrame changedWorld = Renderer3DWorldChunkFrame.fromChunks(
			Arrays.asList(first, chunk(new int[] {2, 0, 2}, new int[] {0, 0, 0}, 203L)));
		assertEquals(
			world.getTextureReferenceSignature(),
			sameWorld.getTextureReferenceSignature(),
			"stable world texture-reference signature");
		assertNotEquals(
			world.getTextureReferenceSignature(),
			changedWorld.getTextureReferenceSignature(),
			"chunk identity invalidates texture-reference signature");

		OpenGLWorldTextureCache cache = new OpenGLWorldTextureCache(null);
		long signature = cacheSignature(cache, frame, world);
		assertEquals(
			signature,
			cacheSignature(cache, sameCatalog, sameWorld),
			"stable cache signature");
		assertNotEquals(
			signature,
			cacheSignature(cache, changedUnreferencedTexture, world),
			"catalog update invalidates cache signature");
		assertNotEquals(
			signature,
			cacheSignature(cache, frame, changedWorld),
			"world update invalidates cache signature");

		long window = 0;
		if (Boolean.getBoolean("material.render")) {
			if (!org.lwjgl.glfw.GLFW.glfwInit()) throw new AssertionError("GLFW init failed");
			org.lwjgl.glfw.GLFW.glfwWindowHint(org.lwjgl.glfw.GLFW.GLFW_VISIBLE, org.lwjgl.glfw.GLFW.GLFW_FALSE);
			window = org.lwjgl.glfw.GLFW.glfwCreateWindow(64, 64, "Material acceptance fixture", 0, 0);
			if (window == 0) throw new AssertionError("hidden OpenGL context failed");
			org.lwjgl.glfw.GLFW.glfwMakeContextCurrent(window);
			org.lwjgl.opengl.GL.createCapabilities();
		}
		try { materialIdentity(frame); } finally {
			if (window != 0) { org.lwjgl.glfw.GLFW.glfwDestroyWindow(window); org.lwjgl.glfw.GLFW.glfwTerminate(); }
		}
		frame.release();
		sameCatalog.release();
		changedUnreferencedTexture.release();
		System.out.println("PASS: OpenGL world texture-reference cache");
	}

	private static void materialIdentity(Renderer3DFrame frame) throws Exception {
		Class<?> builderType = Class.forName("orsc.graphics.three.World$WorldGpuChunkMeshBuilder");
		Constructor<?> ctor = builderType.getDeclaredConstructors()[0];
		ctor.setAccessible(true);
		Method add = builderType.getDeclaredMethod("addFace", Renderer3DModelKind.class,
			int.class, int.class, int[].class, int[].class);
		add.setAccessible(true);
		Method build = builderType.getDeclaredMethod("build");
		build.setAccessible(true);
		OpenGLWorldChunkRenderer renderer = new OpenGLWorldChunkRenderer(null, null, null,
			true, true, true, true, true, true, true);
		Method color = OpenGLWorldChunkRenderer.class.getDeclaredMethod("materialColorForTriangle",
			Renderer3DFrame.class, Renderer3DWorldChunkFrame.ChunkMesh.class, int.class);
		color.setAccessible(true);
		Method raw = OpenGLWorldChunkRenderer.class.getDeclaredMethod("rawMaterialColorForTriangle",
			Renderer3DFrame.class, Renderer3DWorldChunkFrame.ChunkMesh.class, int.class);
		raw.setAccessible(true);
		for (Renderer3DModelKind kind : new Renderer3DModelKind[] {
			Renderer3DModelKind.TERRAIN, Renderer3DModelKind.WALL, Renderer3DModelKind.ROOF}) {
			for (int resource : new int[] {-1, -2, -32, -32768, 0, 1, LEGACY_TRANSPARENT_TEXTURE}) {
				for (boolean back : new boolean[] {false, true}) {
					Object builder = ctor.newInstance(0, 50, 50, 0, 0, false);
					add.invoke(builder, kind, back ? LEGACY_TRANSPARENT_TEXTURE : resource,
						back ? resource : LEGACY_TRANSPARENT_TEXTURE,
						new int[] {0,0,0, 128,0,0, 0,0,128}, new int[] {0,0,0});
					Object mesh = build.invoke(builder);
					Method export = mesh.getClass().getDeclaredMethod("toRenderer3DWorldChunkMesh");
					export.setAccessible(true);
					Renderer3DWorldChunkFrame.ChunkMesh chunk =
						(Renderer3DWorldChunkFrame.ChunkMesh) export.invoke(mesh);
					int expectedTexture = resource < 0 ? LEGACY_TRANSPARENT_TEXTURE : resource;
					int encoded = -(resource + 1);
					int rgb = ((encoded & 0x7c00) << 9) | ((encoded & 0x3e0) << 6) | ((encoded & 31) << 3);
					assertEquals(expectedTexture, chunk.getTriangleTexture(0), kind + " material identity");
					assertEquals(resource < 0 ? rgb : LEGACY_TRANSPARENT_TEXTURE,
						chunk.getTriangleFallbackColor(0), kind + " decoded color");
					if (resource != LEGACY_TRANSPARENT_TEXTURE) {
						int expectedColor = resource < 0 ? rgb : frame.getTexture(resource).getAverageOpaqueRgb();
						assertEquals(expectedColor, ((Integer) color.invoke(renderer, frame, chunk, 0)).intValue(), kind + " classic color");
						assertEquals(expectedColor, ((Integer) raw.invoke(renderer, frame, chunk, 0)).intValue(), kind + " remaster color");
						if (Boolean.getBoolean("material.render")) renderChunk(renderer, frame, chunk);
					}
					if (resource >= 0 && resource != LEGACY_TRANSPARENT_TEXTURE) {
						if (chunk.getVertexTextureU(1) == 0.0f && chunk.getVertexTextureV(1) == 0.0f)
							throw new AssertionError("genuine texture lost UV coordinates");
					}
				}
			}
		}
		// RGB can be any 24-bit value, including every occupied texture slot.
		for (int rgb : new int[] {0, 1, 2, 3, 8, 248}) {
			Renderer3DWorldChunkFrame.ChunkMesh chunk = chunk(new int[] {LEGACY_TRANSPARENT_TEXTURE}, new int[] {rgb}, 900L + rgb);
			assertEquals(rgb, ((Integer) color.invoke(renderer, frame, chunk, 0)).intValue(), "RGB never aliases texture");
			assertEquals(rgb, ((Integer) raw.invoke(renderer, frame, chunk, 0)).intValue(), "raw RGB never aliases texture");
			assertReferences(chunk, new int[] {LEGACY_TRANSPARENT_TEXTURE}, "solid has no texture dependency");
		}
	}

	private static void renderChunk(OpenGLWorldChunkRenderer renderer, Renderer3DFrame frame,
		Renderer3DWorldChunkFrame.ChunkMesh chunk) throws Exception {
		OpenGLWorldTextureCache textureCache = new OpenGLWorldTextureCache(LwjglBindings.load());
		textureCache.uploadReferencedTextures(frame, Renderer3DWorldChunkFrame.fromChunks(java.util.Arrays.asList(chunk)));
		renderer = new OpenGLWorldChunkRenderer(LwjglBindings.load(), textureCache, null,
			true, true, true, true, true, true, true);
		Method ensure = OpenGLWorldChunkRenderer.class.getDeclaredMethod("ensureUploadBuffers", int.class, int.class);
		ensure.setAccessible(true);
		ensure.invoke(renderer, 3, 3);
		Method copy = OpenGLWorldChunkRenderer.class.getDeclaredMethod("copyChunkVertices",
			Renderer3DWorldChunkFrame.ChunkMesh.class, Renderer3DFrame.class, int.class, boolean.class, java.util.List.class);
		copy.setAccessible(true);
		copy.invoke(renderer, chunk, frame, 3, true, java.util.Collections.emptyList());
		java.lang.reflect.Field bufferField = OpenGLWorldChunkRenderer.class.getDeclaredField("vertexUploadBuffer");
		bufferField.setAccessible(true);
		java.nio.FloatBuffer vertices = (java.nio.FloatBuffer) bufferField.get(renderer);
		java.lang.reflect.Field strideField = OpenGLWorldChunkRenderer.class.getDeclaredField("STRIDE_BYTES");
		strideField.setAccessible(true);
		int stride = strideField.getInt(null);
		int vbo = org.lwjgl.opengl.GL15.glGenBuffers();
		org.lwjgl.opengl.GL15.glBindBuffer(org.lwjgl.opengl.GL15.GL_ARRAY_BUFFER, vbo);
		org.lwjgl.opengl.GL15.glBufferData(org.lwjgl.opengl.GL15.GL_ARRAY_BUFFER, vertices, org.lwjgl.opengl.GL15.GL_STATIC_DRAW);
		org.lwjgl.opengl.GL11.glViewport(0, 0, 64, 64);
		org.lwjgl.opengl.GL11.glClearColor(1, 0, 1, 1);
		org.lwjgl.opengl.GL11.glClear(org.lwjgl.opengl.GL11.GL_COLOR_BUFFER_BIT);
		org.lwjgl.opengl.GL11.glMatrixMode(org.lwjgl.opengl.GL11.GL_PROJECTION);
		org.lwjgl.opengl.GL11.glLoadIdentity();
		org.lwjgl.opengl.GL11.glOrtho(0, 128, 0, 128, -1, 1);
		org.lwjgl.opengl.GL11.glMatrixMode(org.lwjgl.opengl.GL11.GL_MODELVIEW);
		org.lwjgl.opengl.GL11.glLoadIdentity();
		org.lwjgl.opengl.GL11.glRotatef(-90, 1, 0, 0);
		org.lwjgl.opengl.GL11.glEnableClientState(org.lwjgl.opengl.GL11.GL_VERTEX_ARRAY);
		org.lwjgl.opengl.GL11.glEnableClientState(org.lwjgl.opengl.GL11.GL_COLOR_ARRAY);
		org.lwjgl.opengl.GL11.glVertexPointer(3, org.lwjgl.opengl.GL11.GL_FLOAT, stride, 0L);
		org.lwjgl.opengl.GL11.glColorPointer(4, org.lwjgl.opengl.GL11.GL_FLOAT, stride, 12L);
		WorldChunkMaterialBatch batch = new WorldChunkMaterialBatch(chunk.getTriangleModelKind(0),
			chunk.getTriangleTexture(0), chunk.getTriangleFallbackColor(0), 0, 3, 0, 0, 0, 128, 0, 0, 0, 128);
		Method stateMethod = OpenGLWorldChunkRenderer.class.getDeclaredMethod("chunkBatchDrawState",
			Renderer3DFrame.class, WorldChunkMaterialBatch.class, boolean.class);
		stateMethod.setAccessible(true);
		WorldChunkBatchDrawState state = (WorldChunkBatchDrawState) stateMethod.invoke(renderer, frame, batch, true);
		boolean textured = chunk.getTriangleTexture(0) != LEGACY_TRANSPARENT_TEXTURE;
		if (state.bindResult != (textured ? WorldChunkBatchBindResult.TEXTURED : WorldChunkBatchBindResult.FLAT_FALLBACK))
			throw new AssertionError("wrong texture-enabled draw state " + state.bindResult);
		Method bind = OpenGLWorldChunkRenderer.class.getDeclaredMethod("bindChunkBatchDrawState",
			WorldChunkBatchDrawState.class, WorldChunkDrawAccumulator.class, boolean.class);
		bind.setAccessible(true);
		bind.invoke(renderer, state, new WorldChunkDrawAccumulator(), false);
		org.lwjgl.opengl.GL11.glDrawArrays(org.lwjgl.opengl.GL11.GL_TRIANGLES, 0, 3);
		java.nio.ByteBuffer pixel = java.nio.ByteBuffer.allocateDirect(4);
		org.lwjgl.opengl.GL11.glReadPixels(16, 16, 1, 1, org.lwjgl.opengl.GL11.GL_RGBA, org.lwjgl.opengl.GL11.GL_UNSIGNED_BYTE, pixel);
		for (int channel = 0; channel < 3; channel++) {
			int expected = textured
				? Math.round(((frame.getTexture(chunk.getTriangleTexture(0)).getAverageOpaqueRgb() >> (16 - channel * 8)) & 255) * vertices.get(9 + channel))
				: Math.round(vertices.get(3 + channel) * 255);
			int actual = pixel.get(channel) & 255;
			if (Math.abs(expected - actual) > 1) throw new AssertionError("GPU pixel mismatch " + expected + " != " + actual);
		}
		org.lwjgl.opengl.GL15.glDeleteBuffers(vbo);
		textureCache.close();
	}

	private static Renderer3DTextureData texture(int textureId, int color)
		throws Exception {
		Method factory = Renderer3DTextureData.class.getDeclaredMethod(
			"fromLegacyResource",
			int.class,
			int.class,
			int[].class);
		factory.setAccessible(true);
		int[] pixels = new int[64 * 64];
		Arrays.fill(pixels, color);
		return (Renderer3DTextureData) factory.invoke(null, textureId, 0, pixels);
	}

	private static Renderer3DFrame frame(Renderer3DTextureData[] textures)
		throws Exception {
		Constructor<Renderer3DFrame> constructor =
			Renderer3DFrame.class.getDeclaredConstructor(
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				int.class,
				Renderer3DTextureData[].class);
		constructor.setAccessible(true);
		return constructor.newInstance(
			0,
			0,
			0,
			512,
			346,
			256,
			173,
			0,
			0,
			0,
			0,
			0,
			0,
			9,
			5,
			textures);
	}

	private static Renderer3DWorldChunkFrame.ChunkMesh chunk(
		int[] triangleTextures,
		int[] triangleFallbackColors,
		long signature) {
		return new Renderer3DWorldChunkFrame.ChunkMesh(
			0,
			50,
			50,
			0,
			0,
			new int[0],
			new float[0],
			new float[0],
			new int[0],
			new int[0],
			triangleTextures,
			triangleFallbackColors,
			new Renderer3DModelKind[triangleTextures.length],
			0,
			0,
			0,
			signature);
	}

	private static long cacheSignature(
		OpenGLWorldTextureCache cache,
		Renderer3DFrame frame,
		Renderer3DWorldChunkFrame world) throws Exception {
		Method method = OpenGLWorldTextureCache.class.getDeclaredMethod(
			"chunkTextureUploadSignature",
			Renderer3DFrame.class,
			Renderer3DWorldChunkFrame.class);
		method.setAccessible(true);
		return ((Long) method.invoke(cache, frame, world)).longValue();
	}

	private static void assertReferences(
		Renderer3DWorldChunkFrame.ChunkMesh chunk,
		int[] expected,
		String label) {
		assertEquals(expected.length, chunk.getReferencedTextureCount(), label + " count");
		for (int index = 0; index < expected.length; index++) {
			assertEquals(expected[index], chunk.getReferencedTextureId(index), label + " id");
		}
	}

	private static void assertReferences(
		Renderer3DWorldChunkFrame frame,
		int[] expected,
		String label) {
		assertEquals(expected.length, frame.getReferencedTextureCount(), label + " count");
		for (int index = 0; index < expected.length; index++) {
			assertEquals(expected[index], frame.getReferencedTextureId(index), label + " id");
		}
	}

	private static void assertSame(Object expected, Object actual, String label) {
		if (expected != actual) {
			throw new AssertionError(label);
		}
	}

	private static void assertEquals(int expected, int actual, String label) {
		if (expected != actual) {
			throw new AssertionError(
				label + ": expected " + expected + " but was " + actual);
		}
	}

	private static void assertEquals(long expected, long actual, String label) {
		if (expected != actual) {
			throw new AssertionError(
				label + ": expected " + expected + " but was " + actual);
		}
	}

	private static void assertNotEquals(long first, long second, String label) {
		if (first == second) {
			throw new AssertionError(label);
		}
	}
}
"""


def require(source: str, fragment: str) -> None:
    if fragment not in source:
        raise AssertionError(f"missing expected source fragment: {fragment!r}")


def main() -> None:
    if not CLIENT_JAR.is_file():
        raise AssertionError(
            f"missing {CLIENT_JAR}; run ./scripts/build-client.sh first"
        )

    frame_source = FRAME_SOURCE.read_text(encoding="utf-8")
    for fragment in (
        ": textures.clone();",
        "this.textureCatalogSignature = textureCatalogSignature(this.textures);",
        "public long getTextureCatalogSignature()",
    ):
        require(frame_source, fragment)

    world_source = WORLD_FRAME_SOURCE.read_text(encoding="utf-8")
    for fragment in (
        "this.referencedTextureIds = collectReferencedTextureIds(",
        "textureReferences.add(chunk.getReferencedTextureId(index));",
        "public long getTextureReferenceSignature()",
    ):
        require(world_source, fragment)

    cache_source = TEXTURE_CACHE_SOURCE.read_text(encoding="utf-8")
    chunk_upload = cache_source.split(
        "WorldTextureUploadStats uploadReferencedTextures(\n"
        "\t\tRenderer3DFrame frame,",
        1,
    )[1].split(
        "private long chunkTextureUploadSignature",
        1,
    )[0]
    require(chunk_upload, "chunkFrame.getReferencedTextureCount()")
    require(chunk_upload, "chunkFrame.getReferencedTextureId(index)")
    if "getTriangleTexture(" in chunk_upload:
        raise AssertionError("chunk texture upload still scans every triangle")

    signature_builder = cache_source.split(
        "private long chunkTextureUploadSignature", 1
    )[1].split("private long mixSignature", 1)[0]
    require(signature_builder, "frame.getTextureCatalogSignature()")
    require(signature_builder, "chunkFrame.getTextureReferenceSignature()")
    if "getTriangleTexture(" in signature_builder:
        raise AssertionError("texture cache signature still scans every triangle")
    if "mixTextureSignature" in cache_source:
        raise AssertionError("obsolete per-texture signature scan remains")

    with tempfile.TemporaryDirectory(
        prefix="opengl-world-texture-reference-cache-"
    ) as raw_temp:
        temp = Path(raw_temp)
        source_dir = temp / "orsc"
        source_dir.mkdir(parents=True)
        fixture = source_dir / "OpenGLWorldTextureReferenceFixture.java"
        fixture.write_text(textwrap.dedent(FIXTURE), encoding="utf-8")

        compile_result = subprocess.run(
            [
                "javac",
                "-source",
                "8",
                "-target",
                "8",
                "-cp",
                str(CLIENT_JAR),
                "-d",
                str(temp),
                str(fixture),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if compile_result.returncode != 0:
            raise AssertionError(
                "texture-reference fixture compile failed:\n"
                + compile_result.stdout
                + compile_result.stderr
            )

        run_result = subprocess.run(
            [
                "java",
                "-Dmaterial.render=" + str("--render" in sys.argv).lower(),
                "-cp",
                os.pathsep.join((str(temp), str(CLIENT_JAR))),
                "orsc.OpenGLWorldTextureReferenceFixture",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if run_result.returncode != 0:
            raise AssertionError(
                "texture-reference fixture failed:\n"
                + run_result.stdout
                + run_result.stderr
            )
        print(run_result.stdout.strip())
        if "--render" in sys.argv:
            print("PASS: hidden OpenGL framebuffer acceptance, production textured/solid batch binding and vertex upload")


if __name__ == "__main__":
    main()

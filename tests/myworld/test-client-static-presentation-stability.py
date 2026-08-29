#!/usr/bin/env python3
"""Keep unchanged scenery baselines from rebuilding resident object chunks."""

from __future__ import annotations

import subprocess
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLIENT_JAR = ROOT / "Client_Base/Open_RSC_Client.jar"
CLIENT = ROOT / "Client_Base/src/orsc/mudclient.java"


FIXTURE = r"""
package orsc;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class StaticPresentationStabilityFixture {
	private StaticPresentationStabilityFixture() {
	}

	public static void main(String[] args) {
		List<SceneBaselineState.Record> original = Arrays.asList(
			new SceneBaselineState.Record(1191, 120, 648, 0, 0),
			new SceneBaselineState.Record(1201, 121, 648, 4, 0));
		List<SceneBaselineState.Record> identical = Arrays.asList(
			new SceneBaselineState.Record(1191, 120, 648, 0, 0),
			new SceneBaselineState.Record(1201, 121, 648, 4, 0));

		assertTrue(mudclient.sameStaticScenePresentationRecords(original, original),
			"same list");
		assertTrue(mudclient.sameStaticScenePresentationRecords(original, identical),
			"equal record content");
		assertTrue(mudclient.sameStaticScenePresentationRecords(
			Collections.<SceneBaselineState.Record>emptyList(),
			Collections.<SceneBaselineState.Record>emptyList()), "empty lists");
		assertFalse(mudclient.sameStaticScenePresentationRecords(original, null),
			"null candidate");
		assertFalse(mudclient.sameStaticScenePresentationRecords(
			original, Collections.singletonList(identical.get(0))), "different size");

		for (int field = 0; field < 5; field++) {
			List<SceneBaselineState.Record> changed = new ArrayList<SceneBaselineState.Record>(identical);
			SceneBaselineState.Record record = identical.get(1);
			changed.set(1, new SceneBaselineState.Record(
				field == 0 ? record.id + 1 : record.id,
				field == 1 ? record.x + 1 : record.x,
				field == 2 ? record.y + 1 : record.y,
				field == 3 ? record.direction + 1 : record.direction,
				field == 4 ? record.type + 1 : record.type));
			assertFalse(mudclient.sameStaticScenePresentationRecords(original, changed),
				"changed record field " + field);
		}
		assertFalse(mudclient.sameStaticScenePresentationRecords(
			original, Arrays.asList(identical.get(1), identical.get(0))),
			"changed canonical order");
	}

	private static void assertTrue(boolean condition, String label) {
		if (!condition) {
			throw new AssertionError(label);
		}
	}

	private static void assertFalse(boolean condition, String label) {
		assertTrue(!condition, label);
	}
}
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    client = CLIENT.read_text(encoding="utf-8")
    replacement = client[
        client.index("public void replaceStaticScenePresentation(") :
        client.index("public void clearStaticScenePresentation()")
    ]
    require(
        "sameStaticScenePresentationRecords(" in replacement,
        "static presentation replacement must compare record content",
    )
    require(
        replacement.index("sameStaticScenePresentationRecords(")
        < replacement.index("this.staticPresentationRevision++;"),
        "unchanged presentation must return before revision invalidation",
    )
    require(CLIENT_JAR.is_file(), "client jar missing; run ./scripts/build-client.sh first")

    with tempfile.TemporaryDirectory(prefix="static-presentation-stability-") as temp_name:
        temp = Path(temp_name)
        source = temp / "orsc/StaticPresentationStabilityFixture.java"
        source.parent.mkdir(parents=True)
        source.write_text(textwrap.dedent(FIXTURE), encoding="utf-8")
        subprocess.run(
            ["javac", "-cp", str(CLIENT_JAR), "-d", str(temp), str(source)],
            check=True,
            cwd=ROOT,
        )
        subprocess.run(
            [
                "java",
                "-cp",
                f"{temp}:{CLIENT_JAR}",
                "orsc.StaticPresentationStabilityFixture",
            ],
            check=True,
            cwd=ROOT,
        )

    print("PASS: unchanged scenery presentation avoids resident chunk rebuilds")


if __name__ == "__main__":
    main()

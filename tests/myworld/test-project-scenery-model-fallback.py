#!/usr/bin/env python3
"""Exercise safe project scenery aliases against the actual archive lookup code."""

from pathlib import Path
import subprocess
import tempfile
import textwrap


ROOT = Path(__file__).resolve().parents[2]
DATA_OPERATIONS = ROOT / "Client_Base/src/com/openrsc/data/DataOperations.java"
DATA_DECRYPTER = ROOT / "Client_Base/src/com/openrsc/data/DataFileDecrypter.java"
DATA_VARIABLES = ROOT / "Client_Base/src/com/openrsc/data/DataFileVariables.java"
RESOLVER = ROOT / "Client_Base/src/orsc/ProjectSceneryModelFallbackResolver.java"
ENTITY_HANDLER = ROOT / "Client_Base/src/com/openrsc/client/entityhandling/EntityHandler.java"
CLIENT = ROOT / "Client_Base/src/orsc/mudclient.java"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> None:
    entity_handler = ENTITY_HANDLER.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")
    require(
        "PROJECT_PACKAGED_MODEL_FALLBACKS.put(id, packaged);" in entity_handler,
        "project scenery replacement must retain the trusted packaged-client identity",
    )
    require(
        "ProjectSceneryModelFallbackResolver.resolve(models, requested," in client,
        "model loading must resolve project aliases against the loaded archive",
    )
    require(
        "PROJECT_SCENERY_MODEL_ALIAS_RESOLVED sceneryId=" in client,
        "model alias activation must leave an actionable deterministic diagnostic",
    )

    harness = textwrap.dedent(
        """
        package orsc;

        public final class ProjectSceneryModelFallbackHarness {
            private static void check(boolean value, String message) {
                if (!value) throw new AssertionError(message);
            }

            private static int hash(String name) {
                int value = 0;
                for (char character : name.toUpperCase().toCharArray()) {
                    value = value * 61 + character - 32;
                }
                return value;
            }

            private static byte[] archive(String... names) {
                byte[] data = new byte[2 + names.length * 10];
                data[0] = (byte) (names.length >>> 8);
                data[1] = (byte) names.length;
                for (int index = 0; index < names.length; index++) {
                    int value = hash(names[index]);
                    int offset = 2 + index * 10;
                    data[offset] = (byte) (value >>> 24);
                    data[offset + 1] = (byte) (value >>> 16);
                    data[offset + 2] = (byte) (value >>> 8);
                    data[offset + 3] = (byte) value;
                }
                return data;
            }

            public static void main(String[] arguments) {
                byte[] packagedOnly = archive("dolmen.ob3");
                check("dolmen".equals(ProjectSceneryModelFallbackResolver.resolve(
                    packagedOnly, "air altar", "dolmen")),
                    "absent project alias did not select the proven packaged model");

                byte[] customPresent = archive("air altar.ob3", "dolmen.ob3");
                check("air altar".equals(ProjectSceneryModelFallbackResolver.resolve(
                    customPresent, "air altar", "dolmen")),
                    "a present project model must win over the packaged fallback");

                check("air altar".equals(ProjectSceneryModelFallbackResolver.resolve(
                    archive("tree.ob3"), "air altar", "dolmen")),
                    "an absent fallback must never fabricate visual evidence");
                check("na".equals(ProjectSceneryModelFallbackResolver.resolve(
                    packagedOnly, "na", "dolmen")),
                    "an explicitly invisible project model must remain invisible");
                check(ProjectSceneryModelFallbackResolver.resolve(
                    packagedOnly, null, "dolmen") == null,
                    "a missing project model must remain missing");
                check("dolmen".equals(ProjectSceneryModelFallbackResolver.resolve(
                    packagedOnly, "dolmen", "dolmen")),
                    "an exact project model must remain unchanged");

                System.out.println("PASS: project scenery model fallback resolver");
            }
        }
        """
    )

    with tempfile.TemporaryDirectory(prefix="world-builder-scenery-fallback-") as raw:
        workspace = Path(raw)
        harness_path = workspace / "orsc/ProjectSceneryModelFallbackHarness.java"
        harness_path.parent.mkdir(parents=True)
        harness_path.write_text(harness, encoding="utf-8")
        classes = workspace / "classes"
        classes.mkdir()
        subprocess.run(
            [
                "javac",
                "-encoding",
                "UTF-8",
                "-d",
                str(classes),
                str(DATA_OPERATIONS),
                str(DATA_DECRYPTER),
                str(DATA_VARIABLES),
                str(RESOLVER),
                str(harness_path),
            ],
            cwd=ROOT,
            check=True,
        )
        completed = subprocess.run(
            ["java", "-cp", str(classes), "orsc.ProjectSceneryModelFallbackHarness"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        require(
            "PASS: project scenery model fallback resolver" in completed.stdout,
            "compiled resolver harness did not complete",
        )

    print("PASS: project scenery aliases retain custom assets and use only proven fallbacks")


if __name__ == "__main__":
    main()

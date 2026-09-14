from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from conflate.build import build_source, run_build
from conflate.compiler import ConflateError


class BuildTests(unittest.TestCase):
    def test_force_rebuild_preserves_unrelated_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "program.confl"
            source.write_text("@python\nx = 1\n", encoding="utf-8")
            output = build_source(source, root / "build")
            build_source(source, output, force=True)
            extra = output / "user-notes.txt"
            extra.write_text("keep me", encoding="utf-8")
            with self.assertRaisesRegex(ConflateError, "unexpected files"):
                build_source(source, output, force=True)
            self.assertEqual(extra.read_text(encoding="utf-8"), "keep me")

    def test_build_does_not_execute_python_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "ran.txt"
            source = root / "program.confl"
            source.write_text(
                "@python\n"
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
                encoding="utf-8",
            )
            output = root / "build"
            build_source(source, output)
            self.assertFalse(marker.exists())
            self.assertTrue((output / "manifest.json").is_file())

    def test_build_rejects_source_errors_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.confl"
            source.write_text("@python\nif True print('bad')\n", encoding="utf-8")
            output = root / "build"
            with self.assertRaises(ConflateError):
                build_source(source, output)
            self.assertFalse(output.exists())

    def test_run_build_validates_source_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "program.confl"
            source.write_text("@python\nprint('before')\n", encoding="utf-8")
            output = build_source(source, root / "build")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            (output / manifest["source"]).write_text("@python\nprint('changed')\n", encoding="utf-8")
            with self.assertRaises(ConflateError):
                run_build(output)

    @unittest.skipUnless(shutil.which("g++"), "g++ is required")
    def test_run_build_executes_and_reuses_native_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "program.confl"
            source.write_text(
                "@python\nx = 40\n@cpp\nint answer = 42;\n"
                "@python\nprint(answer)\n",
                encoding="utf-8",
            )
            output = build_source(source, root / "build")
            cache = output / ".conflate" / "build"
            artifacts = [path for path in cache.rglob("*") if path.is_file() and path.name in {"block", "block.exe"}]
            self.assertTrue(artifacts)
            artifact = artifacts[0]
            before = artifact.stat().st_mtime_ns
            before_paths = {path for path in cache.rglob("*") if path.name != "state.json"}
            run_build(output)
            first = artifact.stat().st_mtime_ns
            time.sleep(0.01)
            run_build(output)
            self.assertEqual(before, first)
            self.assertEqual(first, artifact.stat().st_mtime_ns)
            self.assertEqual(before_paths, {path for path in cache.rglob("*") if path.name != "state.json"})

    def test_public_run_source_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "program.confl"
            source.write_text("@python\nprint('alias works')\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "conflate", "--run-source", str(source)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "alias works\n")


if __name__ == "__main__":
    unittest.main()

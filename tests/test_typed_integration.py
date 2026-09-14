"""End-to-end boundary checks across the real native toolchains."""

import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from conflate.compiler import Runner, compile_executable


class TypedIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("rustc"), "rustc required")
    def test_rust_python_order_validation_example(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "rust-python-orders.confl"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / example.name
            source.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            runner = Runner(source)
            output = io.StringIO()
            with redirect_stdout(output):
                runner.run()
            self.assertEqual(runner.state["totals"], [2598, 1350])
            self.assertEqual(runner.state["rejected"], 3)
            self.assertEqual(output.getvalue(), "Accepted 2 orders; rejected 3\nRevenue: USD 39.48\n")

    @unittest.skipUnless(shutil.which("g++"), "g++ required")
    def test_compiled_launcher_propagates_runtime_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "failure.confl"
            source.write_text("@python(out: value: int)\nvalue = 'wrong'\n", encoding="utf-8")
            executable = source.with_suffix(".exe" if sys.platform == "win32" else "")
            compile_executable(source, executable)
            result = subprocess.run([str(executable)], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output `value` expected int", result.stderr)

    def test_unpublished_native_objects_stay_local(self):
        cases = [
            ("java", "javac", "Object scratch = new Object();\nlong answer = 42;"),
            ("go", "go", "scratch := make(chan int)\n_ = scratch\nanswer := 42"),
            ("rust", "rustc", "let scratch = || 7;\nlet answer: i64 = 42;"),
        ]
        for language, tool, body in cases:
            if not shutil.which(tool):
                continue
            with self.subTest(language=language), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "locals.confl"
                source.write_text(
                    f"@{language}(out: answer: int)\n{body}\n"
                    "@python(in: answer: int)\nassert answer == 42\n",
                    encoding="utf-8",
                )
                runner = Runner(source)
                runner.run()
                self.assertEqual(runner.state, {"answer": 42})

    @unittest.skipUnless(
        all(shutil.which(t) for t in ("g++", "javac", "java", "go", "rustc")),
        "all native toolchains required",
    )
    def test_typed_values_cross_every_builtin_language(self):
        program = """@python(out: seed: int)
seed = 38
private_note = 'must not be published'
@cpp(in: seed: int; out: cpp_value: int)
int cpp_value = seed.as<int>() + 1;
@java(in: cpp_value: int; out: java_value: int)
long java_value = conflateInt(cpp_value) + 1;
@go(in: java_value: int; out: go_value: int)
go_value := conflateInt(java_value) + 1
@rust(in: go_value: int; out: answer: int)
let answer: i64 = go_value.as_i64()? + 1;
@python(in: answer: int)
assert 'seed' not in globals()
assert 'private_note' not in globals()
print(answer)
"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "typed.confl"
            source.write_text(program, encoding="utf-8")
            runner = Runner(source)
            output = io.StringIO()
            with redirect_stdout(output):
                runner.run()
            self.assertEqual(output.getvalue(), "42\n")
            self.assertEqual(runner.state["seed"], 38)
            self.assertEqual(runner.state["answer"], 42)
            self.assertNotIn("private_note", runner.state)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from conflate.compiler import ConflateError, Runner, parse_program


class ParserTests(unittest.TestCase):
    def test_splits_ordered_blocks(self) -> None:
        blocks = parse_program("@python\nx = 1\n@cpp\nstd::cout << x\n")
        self.assertEqual([block.language for block in blocks], ["python", "cpp"])
        self.assertEqual(blocks[1].start_line, 4)

    def test_rejects_code_before_marker(self) -> None:
        with self.assertRaises(ConflateError):
            parse_program("x = 1\n@python\nprint(x)\n")


class RuntimeTests(unittest.TestCase):
    def test_all_five_languages_in_one_program_when_installed(self) -> None:
        tools = ("g++", "javac", "java", "go", "rustc")
        if not all(__import__("shutil").which(tool) for tool in tools):
            self.skipTest("all five language toolchains are required")
        source = Path(__file__).resolve().parents[1] / "examples" / "all-languages.confl"
        result = subprocess.run(
            [sys.executable, "-m", "conflate", "--execute-source", str(source)],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("40, 42, 43, 44, 45", result.stdout)

    def test_java_go_and_rust_round_trip_when_installed(self) -> None:
        cases = [
            ("java", "javac", "System.out.println(message);\nlong answer = conflateInt(seed) + 2;", "Java"),
            ("go", "go", "fmt.Println(message)\nanswer := conflateInt(seed) + 2", "Go"),
            ("rust", "rustc", 'println!("{}", message);\nlet answer: i64 = seed.as_i64()? + 2;', "Rust"),
        ]
        for marker, tool, native_code, label in cases:
            if not __import__("shutil").which(tool):
                continue
            with self.subTest(language=label), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / f"{marker}.confl"
                source.write_text(
                    "@python\nmessage = ['hello', 'languages']\nseed = 40\n"
                    f"@{marker}\n{native_code}\n"
                    f"@python\nprint('{label} returned', answer)\n",
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [sys.executable, "-m", "conflate", "--execute-source", str(source)],
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"{label} returned 42", result.stdout)

    def test_run_rejects_source_file_without_traceback(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows executable validation")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "helloWorld.confl"
            source.write_text("@python\nprint('hello')\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "conflate", "-r", str(source)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("-r expects a compiled .exe", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_python_blocks_share_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "program.cfl"
            source.write_text("@python\nx = 40\n@python\nprint(x + 2)\n", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                Runner(source).run()
            self.assertEqual(output.getvalue(), "42\n")

    @unittest.skipUnless(__import__("shutil").which("g++"), "g++ is required")
    def test_approved_input_example_without_cpp_semicolon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "program.cfl"
            source.write_text(
                "@python\ninp = input().split()\n\n@cpp\nstd::cout << inp\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "-m", "conflate", "--execute-source", str(source)],
                input="hello conflate\n",
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '["hello", "conflate"]')

    @unittest.skipUnless(__import__("shutil").which("g++"), "g++ is required")
    def test_cpp_value_returns_to_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "program.cfl"
            source.write_text(
                "@python\nwords = ['hello', 'world']\n"
                '@cpp\nstd::cout << words << "\\n";\nint answer = 42;\n'
                "@python\nassert answer == 42\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "-m", "conflate", "--execute-source", str(source)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '["hello", "world"]\n')

    @unittest.skipUnless(__import__("shutil").which("g++"), "g++ is required")
    def test_uninitialized_cpp_input_variable_returns_to_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fib.confl"
            source.write_text(
                "@python\n"
                "def fib(n):\n"
                "    return n if n <= 1 else fib(n - 1) + fib(n - 2)\n"
                "@cpp\nint n;\nstd::cin >> n;\n"
                "@python\nprint(fib(n))\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "-m", "conflate", "--execute-source", str(source)],
                input="10\n",
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "55\n")

    @unittest.skipUnless(__import__("shutil").which("g++"), "g++ is required")
    def test_compiled_confl_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "helloWorld.confl"
            executable = root / ("helloWorld.exe" if sys.platform == "win32" else "helloWorld")
            source.write_text(
                "@python\ninp = input().split()\n\n@cpp\nstd::cout << inp\n",
                encoding="utf-8",
            )
            compiled = subprocess.run(
                [sys.executable, "-m", "conflate", "-c", str(source), "-o", str(executable)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run(
                [sys.executable, "-m", "conflate", "-r", str(executable)],
                input="compiled program\n",
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '["compiled", "program"]')


if __name__ == "__main__":
    unittest.main()

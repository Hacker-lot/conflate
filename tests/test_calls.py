import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FunctionTests(unittest.TestCase):
    def run_source(self, source, compile_first=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calls.confl"
            path.write_text(source, encoding="utf-8")
            if compile_first:
                output = path.with_suffix(".exe" if os.name == "nt" else "")
                result = subprocess.run([sys.executable, "-m", "conflate", "-c", str(path)], capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stderr)
                command = [sys.executable, "-m", "conflate", "-r", str(output)]
            else:
                command = [sys.executable, "-m", "conflate", "--execute-source", str(path)]
            return subprocess.run(command, capture_output=True, text=True, timeout=120)

    def test_native_persistence_and_python_callbacks(self):
        cases = {
            "cpp": ("g++", 'int next(int n) { static int count = 0; count += n; return count; }\nint callback(int n) { return twice(n).as<int>(); }', 'int result = callback(21).as<int>();'),
            "java": ("javac", 'static long next(long n) { class Holder { static long count = 0; } Holder.count += n; return Holder.count; }\nstatic long callback(long n) throws Exception { return conflateInt(twice(n)); }', 'long result = conflateInt(callback(21));'),
            "go": ("go", 'func next(n int64) int64 { return n + 1 }\nfunc callback(n int64) int64 { return conflateInt(twice(n)) }', 'result := conflateInt(callback(21))'),
            "rust": ("rustc", 'fn next(n: i64) -> i64 { static COUNT: std::sync::atomic::AtomicI64 = std::sync::atomic::AtomicI64::new(0); COUNT.fetch_add(n, std::sync::atomic::Ordering::SeqCst) + n }\nfn callback(n: i64) -> i64 { twice(n).as_i64().unwrap() }', 'let result: i64 = callback(21).as_i64()?;'),
        }
        for language, (tool, definitions, body) in cases.items():
            if not shutil.which(tool):
                continue
            with self.subTest(language=language):
                expected = "2" if language == "go" else "3"
                source = ("@python\ndef twice(n):\n    return n * 2\n"
                          f"@{language}\n{definitions}\n"
                          "@python\nassert next(1) == " + ("2" if language == "go" else "1") + "\n"
                          f"@{language}\n{body}\n"
                          f"@python\nassert result == 42\nassert next(1) == {('2' if language == 'go' else '2')}\nassert next(1) == {expected}\nprint('calls passed')\n")
                result = self.run_source(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("calls passed", result.stdout)

    @unittest.skipUnless(shutil.which("g++"), "C++ required")
    def test_compiled_functions_and_error_recovery(self):
        source = '''@cpp
int divide(int n) { if (n == 0) throw std::runtime_error("zero rejected"); return 42 / n; }
@python
try:
    divide(0)
except ValueError as error:
    assert 'zero rejected' in str(error)
else:
    raise AssertionError('exception was lost')
assert divide(2) == 21
print('recovered')
'''
        result = self.run_source(source, compile_first=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("recovered", result.stdout)

    @unittest.skipUnless(shutil.which("g++"), "C++ required")
    def test_callback_globals_and_nonportable_error(self):
        result = self.run_source('''@python
counter = 0
def increment():
    global counter
    counter += 1
    return counter
def bad_result():
    return object()
@cpp
int first = increment().as<int>();
int second = increment().as<int>();
try { bad_result(); throw std::runtime_error("missing error"); }
catch (const std::exception& error) { std::cout << error.what() << "\\n"; }
@python
assert (first, second, counter) == (1, 2, 2)
print('globals survived')
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not JSON serializable", result.stdout)
        self.assertIn("globals survived", result.stdout)

    def test_registration_and_external_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {**os.environ, "CONFLATE_CONFIG": str(root / "languages.json")}
            def cli(*args):
                return subprocess.run([sys.executable, "-m", "conflate", *args], env=env, capture_output=True, text=True, timeout=30)
            registered = cli("--add-language", "mypython", sys.executable)
            self.assertEqual(registered.returncode, 0, registered.stderr)
            source = root / "program.confl"
            source.write_text("@mypython\nx = 42\n@python\nassert x == 42\n")
            result = cli("--execute-source", str(source))
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"name": "raw", "extension": ".py", "run": [sys.executable, "{source}", "{state}"]}))
            self.assertEqual(cli("--language-manifest", str(manifest)).returncode, 0)
            source.write_text('@python\nx = 40\n@raw\nimport json, sys\nfrom pathlib import Path\np = Path(sys.argv[1])\ns = json.loads(p.read_text())\ns["x"] += 2\np.write_text(json.dumps(s))\n@python\nassert x == 42\n')
            result = cli("--execute-source", str(source))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(cli("--remove-language", "raw").returncode, 0)
            self.assertNotEqual(cli("--execute-source", str(source)).returncode, 0)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_register_node_and_persistent_javascript_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {**os.environ, "CONFLATE_CONFIG": str(root / "languages.json")}
            registered = subprocess.run([sys.executable, "-m", "conflate", "--add-language", "javascript", shutil.which("node")], env=env, capture_output=True, text=True)
            self.assertEqual(registered.returncode, 0, registered.stderr)
            path = root / "node.confl"
            path.write_text('''@python
def twice(n):
    return n * 2
@javascript
function count(n) { count.total = (count.total || 0) + n; return count.total; }
function callback(n) { return twice(n); }
let answer = callback(21);
@python
assert answer == 42
assert count(1) == 1
assert count(2) == 3
print('node passed')
''')
            result = subprocess.run([sys.executable, "-m", "conflate", "-c", str(path)], env=env, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            executable = path.with_suffix(".exe" if os.name == "nt" else "")
            result = subprocess.run([sys.executable, "-m", "conflate", "-r", str(executable)], env=env, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("node passed", result.stdout)

    @unittest.skipUnless(all(shutil.which(t) for t in ("g++", "javac", "go", "rustc")), "all native toolchains required")
    def test_nested_call_through_all_languages(self):
        result = self.run_source('''@python
def finish(n):
    return n + 1
@rust
fn from_rust(n: i64) -> i64 { finish(n).as_i64().unwrap() + 1 }
@go
func from_go(n int64) int64 { return conflateInt(from_rust(n)) + 1 }
@java
static long from_java(long n) throws Exception { return conflateInt(from_go(n)) + 1; }
@cpp
int from_cpp(int n) { return from_java(n).as<int>() + 1; }
@python
assert from_cpp(37) == 42
print('nested chain passed')
''', compile_first=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nested chain passed", result.stdout)


if __name__ == "__main__":
    unittest.main()

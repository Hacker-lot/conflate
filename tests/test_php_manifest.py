import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _php8_available():
    executable = shutil.which("php")
    if not executable:
        return False
    try:
        result = subprocess.run(
            [executable, "-r", "exit(PHP_VERSION_ID < 80000 ? 1 : 0);"],
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


class PhpManifestTests(unittest.TestCase):
    @unittest.skipUnless(_php8_available(), "PHP 8 required")
    def test_php_manifest_roundtrip_and_error_exit(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            config_root = Path(directory)
            env = {**os.environ, "CONFLATE_CONFIG": str(config_root / "languages.json")}

            registered = subprocess.run(
                [sys.executable, "-m", "conflate", "--language-manifest", str(root / "examples" / "php-language.json")],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)

            source = config_root / "php-roundtrip.confl"
            source.write_text((root / "examples" / "php-roundtrip.confl").read_text(encoding="utf-8"), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "conflate", "--execute-source", str(source)],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PHP computed 42", result.stdout)
            self.assertIn("Conflate via PHP: 42", result.stdout)

            no_output = config_root / "no-output.confl"
            no_output.write_text(
                "@python(out: marker: str)\n"
                "marker = 'kept'\n"
                "@php()\n"
                "echo 'PHP produced no state\\n';\n"
                "@python(in: marker: str)\n"
                "print(marker)\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "-m", "conflate", "--execute-source", str(no_output)],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PHP produced no state", result.stdout)
            self.assertIn("kept", result.stdout)

            collision = config_root / "collision.confl"
            collision.write_text(
                "@python(out: argv: str)\n"
                "argv = 'reserved'\n"
                "@php(in: argv: str)\n"
                "echo 'should not run\\n';\n",
                encoding="utf-8",
            )
            failed = subprocess.run(
                [sys.executable, "-m", "conflate", "--execute-source", str(collision)],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(failed.returncode, 0)

            bad = config_root / "bad.confl"
            bad.write_text("@php\nthis is not valid PHP\n", encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, "-m", "conflate", "--execute-source", str(bad)],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(failed.returncode, 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import __version__
from .compiler import ConflateError, Runner, check_file, compile_executable
from .languages import register, registrations, save, add_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conflate",
        description="Compile and run programs made from multiple programming languages.",
    )
    parser.add_argument("--version", action="version", version=f"Conflate {__version__}")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("-c", "--compile", dest="compile_source", type=Path, metavar="FILE.CONFL")
    action.add_argument("-r", "--run", dest="run_executable", type=Path, metavar="FILE.EXE")
    action.add_argument("--check", dest="check_source", type=Path, metavar="FILE.CONFL")
    action.add_argument("--add-language", nargs=2, metavar=("NAME", "COMPILER"))
    action.add_argument("--remove-language", metavar="NAME")
    action.add_argument("--list-languages", action="store_true")
    action.add_argument("--language-manifest", type=Path)
    parser.add_argument("--backend", choices=["python", "cpp", "java", "go", "rust", "javascript"])
    action.add_argument(
        "--execute-source",
        dest="run_source",
        type=Path,
        metavar="FILE.CONFL",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("-o", "--output", type=Path, help="output path used with -c")
    parser.add_argument("--force", action="store_true", help="replace an existing output")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.add_language:
            entry = register(*arguments.add_language, arguments.backend)
            print(f"Registered @{arguments.add_language[0]} using {entry['compiler']} ({entry['backend']})")
            return 0
        if arguments.language_manifest:
            print(f"Registered @{add_manifest(arguments.language_manifest)}")
            return 0
        if arguments.remove_language:
            entries = registrations()
            if arguments.remove_language not in entries:
                raise ConflateError(f"no registered language: {arguments.remove_language}")
            del entries[arguments.remove_language]
            save(entries)
            return 0
        if arguments.list_languages:
            print("Built in: python, cpp, rust, java, go")
            for name, entry in registrations().items():
                print(f"@{name}: {entry['backend']} {entry.get('compiler', entry.get('run'))}")
            return 0
        if arguments.compile_source is not None:
            source = arguments.compile_source
            if not source.is_file():
                raise ConflateError(f"file not found: {source}")
            default_suffix = ".exe" if sys.platform == "win32" else ""
            output = arguments.output or source.with_suffix(default_suffix)
            compiled = compile_executable(source, output, force=arguments.force)
            print(f"Compiled {source} -> {compiled}")
            return 0

        if arguments.run_executable is not None:
            executable = arguments.run_executable.resolve()
            if not executable.is_file():
                raise ConflateError(f"file not found: {arguments.run_executable}")
            if sys.platform == "win32" and executable.suffix.lower() != ".exe":
                raise ConflateError(
                    f"-r expects a compiled .exe, not {executable.suffix or 'a source file'}; "
                    f"use: conflate -c {arguments.run_executable}"
                )
            try:
                return subprocess.run([str(executable)]).returncode
            except OSError as error:
                raise ConflateError(f"cannot run {executable}: {error}") from error

        source = arguments.run_source or arguments.check_source
        if source is None or not source.is_file():
            raise ConflateError(f"file not found: {source}")
        if arguments.run_source is not None:
            Runner(source).run()
        else:
            blocks = check_file(source)
            print(f"OK: {len(blocks)} language block(s)")
        return 0
    except (ConflateError, ValueError, OSError) as error:
        print(f"conflate: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

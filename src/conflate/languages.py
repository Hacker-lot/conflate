"""User toolchains, stored as data rather than changes to Conflate."""
from __future__ import annotations

import json
import os
import re
import shutil
from contextvars import ContextVar
from pathlib import Path

active_toolchain: ContextVar[dict] = ContextVar("active_toolchain", default={})


def tool(name: str) -> str | None:
    entry = active_toolchain.get()
    backend = {"javac": "java", "rustc": "rust", "node": "javascript"}.get(name, name)
    if entry.get("backend") != backend:
        return None
    return entry.get("runtime" if name == "java" else "compiler")


def config_path() -> Path:
    return Path(os.environ.get("CONFLATE_CONFIG", Path.home() / ".conflate" / "languages.json"))


def registrations() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid language configuration: {path}")
    return data


def register(name: str, compiler: str, backend: str | None = None) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9_+-]*", name):
        raise ValueError("language name must start with a lowercase letter")
    resolved = shutil.which(compiler)
    if not resolved:
        raise ValueError(f"compiler or interpreter not found: {compiler}")
    executable = Path(resolved).stem.lower()
    if backend is None:
        for candidate, pattern in {
            "python": r"python[\d.]*", "cpp": r"(?:g\+\+|clang\+\+)(?:-[\d.]+)?",
            "rust": r"rustc", "java": r"javac", "go": r"go", "javascript": r"node(?:js)?",
        }.items():
            if re.fullmatch(pattern, executable):
                backend = candidate
                break
    if backend not in {"python", "cpp", "rust", "java", "go", "javascript"}:
        raise ValueError("unknown compiler conventions; use --backend for a compatible toolchain, "
                         "or --language-manifest for a new language")
    entry = {"backend": backend, "compiler": str(Path(resolved).resolve())}
    if backend == "java":
        runtime = Path(resolved).with_name("java.exe" if os.name == "nt" else "java")
        if not runtime.exists():
            raise ValueError(f"Java runtime missing next to compiler: {runtime}")
        entry["runtime"] = str(runtime)
    data = registrations()
    data[name] = entry
    save(data)
    return entry


def save(data: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def add_manifest(path: Path) -> str:
    entry = json.loads(path.read_text(encoding="utf-8"))
    name = entry.pop("name", "")
    if not re.fullmatch(r"[a-z][a-z0-9_+-]*", name):
        raise ValueError("manifest requires a valid language name")
    for key in ("run",):
        if not isinstance(entry.get(key), list) or not entry[key] or not all(isinstance(x, str) for x in entry[key]):
            raise ValueError(f"manifest {key} must be a nonempty command array")
    if "compile" in entry and (not isinstance(entry["compile"], list) or not all(isinstance(x, str) for x in entry["compile"])):
        raise ValueError("manifest compile must be a command array")
    if not re.fullmatch(r"\.[a-zA-Z0-9]+", entry.get("extension", "")):
        raise ValueError("manifest requires a source extension, such as .js")
    entry["backend"] = "external"
    data = registrations()
    data[name] = entry
    save(data)
    return name

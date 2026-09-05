from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .foreign import BackendError, ensure_go, ensure_java, ensure_rust, ensure_javascript
from .languages import registrations, active_toolchain, tool
from .calls import Calls, extract, decorate, split_globals, worker_source


class ConflateError(Exception):
    """A user-facing Conflate error."""


@dataclass(frozen=True)
class Block:
    language: str
    source: str
    start_line: int


MARKER = re.compile(r"^\s*@([A-Za-z][A-Za-z0-9_+-]*)\s*$")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LANGUAGES = {
    "python": "python",
    "py": "python",
    "cpp": "cpp",
    "c++": "cpp",
    "rust": "rust",
    "rs": "rust",
    "java": "java",
    "go": "go",
    "golang": "go",
}
CPP_DECLARATION = re.compile(
    r"(?m)^(?:const\s+)?(?:auto|bool|char|short|int|long(?:\s+long)?|float|double|"
    r"std::string|string|conflate::Value)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|\{|;)"
)


def parse_program(text: str, filename: str = "<conflate>") -> list[Block]:
    configured = registrations()
    blocks: list[Block] = []
    language: str | None = None
    block_start = 0
    lines: list[str] = []

    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        marker = MARKER.match(line.rstrip("\r\n"))
        if marker:
            if language is not None:
                blocks.append(Block(language, "".join(lines), block_start))
            language = marker.group(1).lower()
            block_start = line_number + 1
            lines = []
        elif language is None:
            if line.strip() and not line.lstrip().startswith("#"):
                raise ConflateError(
                    f"{filename}:{line_number}: code must follow a language marker such as @python"
                )
        else:
            lines.append(line)

    if language is not None:
        blocks.append(Block(language, "".join(lines), block_start))
    if not blocks:
        raise ConflateError(f"{filename}: no language blocks found")

    for block in blocks:
        if block.language not in LANGUAGES and block.language not in configured:
            raise ConflateError(
                f"{filename}:{block.start_line - 1}: unsupported language @{block.language}"
            )
    return blocks


def language_for(marker):
    entry = registrations().get(marker, {})
    active_toolchain.set(entry)
    return entry.get("backend", LANGUAGES.get(marker, "external"))


def prepare_program(blocks):
    prepared, functions = [], []
    for index, block in enumerate(blocks, 1):
        language = language_for(block.language)
        source, found = extract(block.source, language, index)
        prepared.append(Block(block.language, source, block.start_line))
        functions.extend(found)
    names = [f.name for f in functions]
    if len(names) != len(set(names)):
        raise ConflateError("exported function names must be unique across language blocks")
    return prepared, functions


def _portable_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_portable_value(item, f"{path}[]") for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _portable_value(item, f"{path}.{key}") for key, item in value.items()}
    raise TypeError(f"{path} has unsupported type {type(value).__name__}")


def _snapshot_python_environment(environment: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for name, value in environment.items():
        if name.startswith("__"):
            continue
        try:
            state[name] = _portable_value(value, name)
        except TypeError:
            # Modules, functions, classes, and other Python-only objects stay inside Python.
            continue
    return state


def _cpp_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _cpp_value(value: Any) -> str:
    if value is None:
        return "conflate::Value(nullptr)"
    if value is True:
        return "conflate::Value(true)"
    if value is False:
        return "conflate::Value(false)"
    if isinstance(value, int):
        return f"conflate::Value(static_cast<std::int64_t>({value}))"
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ConflateError("NaN and infinity cannot cross a language boundary yet")
        return f"conflate::Value({value!r})"
    if isinstance(value, str):
        return f"conflate::Value(std::string({_cpp_string(value)}))"
    if isinstance(value, list):
        items = ", ".join(_cpp_value(item) for item in value)
        return f"conflate::Value(conflate::Value::array_t{{{items}}})"
    if isinstance(value, dict):
        items = ", ".join(
            "{" + _cpp_string(key) + ", " + _cpp_value(item) + "}"
            for key, item in value.items()
        )
        return f"conflate::Value(conflate::Value::object_t{{{items}}})"
    raise ConflateError(f"cannot transfer {type(value).__name__} to C++")


def _normalize_cpp(source: str) -> str:
    """Allow an omitted semicolon on an obvious one-line expression."""
    normalized: list[str] = []
    for line in source.splitlines(keepends=True):
        ending = "\n" if line.endswith("\n") else ""
        content = line[:-1] if ending else line
        stripped = content.strip()
        should_end = (
            stripped
            and not stripped.startswith(("#", "//"))
            and not stripped.endswith((";", "{", "}", ":", ",", "\\"))
            and not re.match(r"^(if|for|while|switch|else|do|try|catch)\b", stripped)
        )
        normalized.append(content + (";" if should_end else "") + ending)
    return "".join(normalized)


CPP_RUNTIME = r'''
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

namespace conflate {

class Value {
public:
    using array_t = std::vector<Value>;
    using object_t = std::map<std::string, Value>;
    using storage_t = std::variant<std::nullptr_t, bool, std::int64_t, double,
                                   std::string, array_t, object_t>;

    Value() : data_(nullptr) {}
    Value(std::nullptr_t) : data_(nullptr) {}
    Value(bool value) : data_(value) {}
    Value(char value) : data_(static_cast<std::int64_t>(value)) {}
    Value(short value) : data_(static_cast<std::int64_t>(value)) {}
    Value(int value) : data_(static_cast<std::int64_t>(value)) {}
    Value(long value) : data_(static_cast<std::int64_t>(value)) {}
    Value(long long value) : data_(static_cast<std::int64_t>(value)) {}
    Value(unsigned value) : data_(static_cast<std::int64_t>(value)) {}
    Value(unsigned long value) : data_(static_cast<std::int64_t>(value)) {}
    Value(unsigned long long value) : data_(static_cast<std::int64_t>(value)) {}
    Value(float value) : data_(static_cast<double>(value)) {}
    Value(double value) : data_(value) {}
    Value(const char* value) : data_(std::string(value)) {}
    Value(std::string value) : data_(std::move(value)) {}
    Value(array_t value) : data_(std::move(value)) {}
    Value(object_t value) : data_(std::move(value)) {}

    const storage_t& data() const { return data_; }

    template <typename T>
    T as() const;

private:
    storage_t data_;
};

template <> inline bool Value::as<bool>() const { return std::get<bool>(data_); }
template <> inline std::int64_t Value::as<std::int64_t>() const { return std::get<std::int64_t>(data_); }
template <> inline int Value::as<int>() const { return static_cast<int>(std::get<std::int64_t>(data_)); }
template <> inline double Value::as<double>() const {
    if (auto value = std::get_if<double>(&data_)) return *value;
    return static_cast<double>(std::get<std::int64_t>(data_));
}
template <> inline std::string Value::as<std::string>() const { return std::get<std::string>(data_); }
template <> inline Value::array_t Value::as<Value::array_t>() const { return std::get<array_t>(data_); }
template <> inline Value::object_t Value::as<Value::object_t>() const { return std::get<object_t>(data_); }

class JsonParser {
public:
    explicit JsonParser(std::string text) : text_(std::move(text)) {}

    Value parse() {
        Value result = parse_value();
        whitespace();
        if (position_ != text_.size()) fail("unexpected trailing data");
        return result;
    }

private:
    std::string text_;
    std::size_t position_ = 0;

    [[noreturn]] void fail(const std::string& message) const {
        throw std::runtime_error("invalid shared state at byte " +
                                 std::to_string(position_) + ": " + message);
    }

    void whitespace() {
        while (position_ < text_.size() &&
               (text_[position_] == ' ' || text_[position_] == '\n' ||
                text_[position_] == '\r' || text_[position_] == '\t')) {
            ++position_;
        }
    }

    char take() {
        if (position_ >= text_.size()) fail("unexpected end of input");
        return text_[position_++];
    }

    void expect(char wanted) {
        whitespace();
        if (take() != wanted) fail(std::string("expected '") + wanted + "'");
    }

    bool consume(const std::string& token) {
        whitespace();
        if (text_.compare(position_, token.size(), token) != 0) return false;
        position_ += token.size();
        return true;
    }

    static int hex_digit(char value) {
        if (value >= '0' && value <= '9') return value - '0';
        if (value >= 'a' && value <= 'f') return value - 'a' + 10;
        if (value >= 'A' && value <= 'F') return value - 'A' + 10;
        return -1;
    }

    void append_utf8(std::string& output, unsigned codepoint) {
        if (codepoint <= 0x7f) output += static_cast<char>(codepoint);
        else if (codepoint <= 0x7ff) {
            output += static_cast<char>(0xc0 | (codepoint >> 6));
            output += static_cast<char>(0x80 | (codepoint & 0x3f));
        } else {
            output += static_cast<char>(0xe0 | (codepoint >> 12));
            output += static_cast<char>(0x80 | ((codepoint >> 6) & 0x3f));
            output += static_cast<char>(0x80 | (codepoint & 0x3f));
        }
    }

    std::string parse_string() {
        whitespace();
        if (take() != '"') fail("expected string");
        std::string output;
        while (true) {
            char value = take();
            if (value == '"') return output;
            if (value != '\\') {
                output += value;
                continue;
            }
            char escape = take();
            switch (escape) {
                case '"': output += '"'; break;
                case '\\': output += '\\'; break;
                case '/': output += '/'; break;
                case 'b': output += '\b'; break;
                case 'f': output += '\f'; break;
                case 'n': output += '\n'; break;
                case 'r': output += '\r'; break;
                case 't': output += '\t'; break;
                case 'u': {
                    unsigned codepoint = 0;
                    for (int index = 0; index < 4; ++index) {
                        int digit = hex_digit(take());
                        if (digit < 0) fail("invalid unicode escape");
                        codepoint = (codepoint << 4) | static_cast<unsigned>(digit);
                    }
                    append_utf8(output, codepoint);
                    break;
                }
                default: fail("invalid string escape");
            }
        }
    }

    Value parse_number() {
        whitespace();
        const std::size_t start = position_;
        if (position_ < text_.size() && text_[position_] == '-') ++position_;
        while (position_ < text_.size() && text_[position_] >= '0' && text_[position_] <= '9') ++position_;
        bool floating = false;
        if (position_ < text_.size() && text_[position_] == '.') {
            floating = true;
            ++position_;
            while (position_ < text_.size() && text_[position_] >= '0' && text_[position_] <= '9') ++position_;
        }
        if (position_ < text_.size() && (text_[position_] == 'e' || text_[position_] == 'E')) {
            floating = true;
            ++position_;
            if (position_ < text_.size() && (text_[position_] == '+' || text_[position_] == '-')) ++position_;
            while (position_ < text_.size() && text_[position_] >= '0' && text_[position_] <= '9') ++position_;
        }
        const std::string token = text_.substr(start, position_ - start);
        try {
            return floating ? Value(std::stod(token)) : Value(std::stoll(token));
        } catch (...) {
            fail("invalid number");
        }
    }

    Value parse_array() {
        expect('[');
        Value::array_t output;
        whitespace();
        if (position_ < text_.size() && text_[position_] == ']') {
            ++position_;
            return output;
        }
        while (true) {
            output.push_back(parse_value());
            whitespace();
            char separator = take();
            if (separator == ']') return output;
            if (separator != ',') fail("expected ',' or ']'");
        }
    }

    Value parse_object() {
        expect('{');
        Value::object_t output;
        whitespace();
        if (position_ < text_.size() && text_[position_] == '}') {
            ++position_;
            return output;
        }
        while (true) {
            std::string key = parse_string();
            expect(':');
            output.emplace(std::move(key), parse_value());
            whitespace();
            char separator = take();
            if (separator == '}') return output;
            if (separator != ',') fail("expected ',' or '}'");
        }
    }

    Value parse_value() {
        whitespace();
        if (position_ >= text_.size()) fail("expected value");
        switch (text_[position_]) {
            case '"': return Value(parse_string());
            case '[': return parse_array();
            case '{': return parse_object();
            case 't': if (consume("true")) return Value(true); break;
            case 'f': if (consume("false")) return Value(false); break;
            case 'n': if (consume("null")) return Value(nullptr); break;
            default:
                if (text_[position_] == '-' ||
                    (text_[position_] >= '0' && text_[position_] <= '9')) return parse_number();
        }
        fail("expected value");
    }
};

inline Value::object_t read_state(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read shared state");
    std::ostringstream contents;
    contents << input.rdbuf();
    return JsonParser(contents.str()).parse().as<Value::object_t>();
}

inline std::string escape_json(const std::string& input) {
    std::string output;
    for (unsigned char character : input) {
        switch (character) {
            case '"': output += "\\\""; break;
            case '\\': output += "\\\\"; break;
            case '\b': output += "\\b"; break;
            case '\f': output += "\\f"; break;
            case '\n': output += "\\n"; break;
            case '\r': output += "\\r"; break;
            case '\t': output += "\\t"; break;
            default:
                if (character < 0x20) {
                    const char* digits = "0123456789abcdef";
                    output += "\\u00";
                    output += digits[(character >> 4) & 0xf];
                    output += digits[character & 0xf];
                } else {
                    output += static_cast<char>(character);
                }
        }
    }
    return output;
}

inline void write_json(std::ostream& output, const Value& value);

inline void write_json(std::ostream& output, const Value& value) {
    std::visit([&output](const auto& item) {
        using T = std::decay_t<decltype(item)>;
        if constexpr (std::is_same_v<T, std::nullptr_t>) output << "null";
        else if constexpr (std::is_same_v<T, bool>) output << (item ? "true" : "false");
        else if constexpr (std::is_same_v<T, std::int64_t>) output << item;
        else if constexpr (std::is_same_v<T, double>) output << std::setprecision(17) << item;
        else if constexpr (std::is_same_v<T, std::string>) output << '"' << escape_json(item) << '"';
        else if constexpr (std::is_same_v<T, Value::array_t>) {
            output << '[';
            bool first = true;
            for (const auto& child : item) {
                if (!first) output << ',';
                first = false;
                write_json(output, child);
            }
            output << ']';
        } else if constexpr (std::is_same_v<T, Value::object_t>) {
            output << '{';
            bool first = true;
            for (const auto& [key, child] : item) {
                if (!first) output << ',';
                first = false;
                output << '"' << escape_json(key) << "\":";
                write_json(output, child);
            }
            output << '}';
        }
    }, value.data());
}

inline void write_json(std::ostream& output, const std::string& value) {
    write_json(output, Value(value));
}
inline void write_json(std::ostream& output, const char* value) { write_json(output, Value(value)); }
inline void write_json(std::ostream& output, bool value) { write_json(output, Value(value)); }
template <typename T, std::enable_if_t<std::is_integral_v<T> && !std::is_same_v<T, bool>, int> = 0>
inline void write_json(std::ostream& output, T value) { write_json(output, Value(static_cast<long long>(value))); }
template <typename T, std::enable_if_t<std::is_floating_point_v<T>, int> = 0>
inline void write_json(std::ostream& output, T value) { write_json(output, Value(static_cast<double>(value))); }
template <typename T>
inline void write_json(std::ostream& output, const std::vector<T>& values) {
    output << '[';
    bool first = true;
    for (const auto& value : values) {
        if (!first) output << ',';
        first = false;
        write_json(output, value);
    }
    output << ']';
}

inline void display(std::ostream& output, const Value& value, bool nested) {
    std::visit([&output, nested](const auto& item) {
        using T = std::decay_t<decltype(item)>;
        if constexpr (std::is_same_v<T, std::nullptr_t>) output << "None";
        else if constexpr (std::is_same_v<T, bool>) output << (item ? "true" : "false");
        else if constexpr (std::is_same_v<T, std::int64_t> || std::is_same_v<T, double>) output << item;
        else if constexpr (std::is_same_v<T, std::string>) {
            if (nested) output << '"';
            output << item;
            if (nested) output << '"';
        } else if constexpr (std::is_same_v<T, Value::array_t>) {
            output << '[';
            bool first = true;
            for (const auto& child : item) {
                if (!first) output << ", ";
                first = false;
                display(output, child, true);
            }
            output << ']';
        } else if constexpr (std::is_same_v<T, Value::object_t>) {
            output << '{';
            bool first = true;
            for (const auto& [key, child] : item) {
                if (!first) output << ", ";
                first = false;
                output << '"' << key << "\": ";
                display(output, child, true);
            }
            output << '}';
        }
    }, value.data());
}

inline std::ostream& operator<<(std::ostream& output, const Value& value) {
    display(output, value, false);
    return output;
}

} // namespace conflate
'''


def _generated_cpp(
    block: Block,
    state: dict[str, Any],
    source_path: Path,
) -> tuple[str, list[str]]:
    globals_source, block_source = split_globals(block.source)
    valid_state = {name: value for name, value in state.items() if IDENTIFIER.match(name)}
    includes: list[str] = []
    body_lines: list[str] = []
    for line in block_source.splitlines(keepends=True):
        if line.lstrip().startswith("#include"):
            includes.append(line.strip())
            body_lines.append("\n" if line.endswith("\n") else "")
        else:
            body_lines.append(line)
    body = _normalize_cpp("".join(body_lines))
    declarations = set(CPP_DECLARATION.findall(body))
    names = sorted(set(valid_state) | declarations)

    bindings = "\n".join(
        f'    conflate::Value {name} = _conflate_input_state.at("{name}");'
        for name in sorted(valid_state)
        if name not in declarations
    )
    state_writes: list[str] = []
    for index, name in enumerate(names):
        comma = "" if index == 0 else ","
        state_writes.append(
            f'        _conflate_state << "{comma}\\"{name}\\":"; '
            f"conflate::write_json(_conflate_state, {name});"
        )
    escaped_path = str(source_path.resolve()).replace("\\", "\\\\").replace('"', '\\"')
    generated = f"""{os.linesep.join(includes)}
{CPP_RUNTIME}
{globals_source}

int main(int argc, char** argv) {{
    if (argc != 2) {{
        std::cerr << "conflate: missing state-file argument\\n";
        return 2;
    }}
    const auto _conflate_input_state = conflate::read_state(argv[1]);
{bindings}
#line {block.start_line} "{escaped_path}"
{body}
#line 1 "<conflate-generated>"
    std::ofstream _conflate_state(argv[1], std::ios::binary | std::ios::trunc);
    if (!_conflate_state) {{
        std::cerr << "conflate: cannot write shared state\\n";
        return 3;
    }}
    _conflate_state << "{{";
{os.linesep.join(state_writes)}
    _conflate_state << "}}";
    return 0;
}}
"""
    return generated, names


def _cpp_compiler() -> str:
    if tool("cpp"):
        return tool("cpp")
    compiler = os.environ.get("CXX") or shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise ConflateError("no C++ compiler found; install g++ or clang++, or set CXX")
    return compiler


def _ensure_cpp_executable(
    block: Block,
    index: int,
    state_names: set[str],
    source_path: Path,
    build_root: Path,
) -> tuple[Path, Path, list[str]]:
    placeholder_state = {name: None for name in state_names}
    source, output_names = _generated_cpp(block, placeholder_state, source_path)
    digest = hashlib.sha256((source + _cpp_compiler()).encode("utf-8")).hexdigest()[:16]
    block_dir = build_root / f"cpp-{index}-{digest}"
    block_dir.mkdir(parents=True, exist_ok=True)
    generated_path = block_dir / "block.cpp"
    executable = block_dir / ("block.exe" if os.name == "nt" else "block")
    state_path = block_dir / "state.json"

    if not executable.exists():
        generated_path.write_text(source, encoding="utf-8")
        compile_result = subprocess.run(
            [_cpp_compiler(), "-std=c++20", "-O0", "-pipe", str(generated_path), "-o", str(executable)],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if compile_result.returncode:
            raise ConflateError(f"C++ compilation failed with exit code {compile_result.returncode}")
    return executable, state_path, output_names


class _PythonAssignedNames(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.names.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_ListComp(self, node: ast.ListComp) -> None:
        return

    def visit_SetComp(self, node: ast.SetComp) -> None:
        return

    def visit_DictComp(self, node: ast.DictComp) -> None:
        return

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        return


def _python_assigned_names(block: Block, source_path: Path) -> set[str]:
    try:
        tree = ast.parse(block.source, filename=str(source_path))
    except SyntaxError as error:
        raise ConflateError(f"Python syntax error: {error}") from error
    collector = _PythonAssignedNames()
    collector.visit(tree)
    return collector.names


def _ensure_foreign_artifact(
    language: str,
    block: Block,
    index: int,
    state_names: set[str],
    build_root: Path,
):
    try:
        if language == "javascript":
            return ensure_javascript(block.source, index, state_names, build_root)
        if language == "java":
            return ensure_java(block.source, index, state_names, build_root)
        if language == "go":
            return ensure_go(block.source, index, state_names, build_root)
        return ensure_rust(block.source, index, state_names, build_root)
    except BackendError as error:
        raise ConflateError(str(error)) from error


def _precompile_native_blocks(source: str, runtime_source_path: Path) -> None:
    blocks, functions = prepare_program(parse_program(source, str(runtime_source_path)))
    build_root = runtime_source_path.parent / ".conflate" / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    names: set[str] = set()
    for index, block in enumerate(blocks, start=1):
        language = language_for(block.language)
        if language not in {"python", "external"}:
            block = Block(block.language, decorate(block.source, language, functions), block.start_line)
        if language == "python":
            names.update(_python_assigned_names(block, runtime_source_path))
        elif language == "cpp":
            _, _, output_names = _ensure_cpp_executable(
                block, index, names, runtime_source_path, build_root
            )
            names = set(output_names)
        elif language != "external":
            names = set(
                _ensure_foreign_artifact(language, block, index, names, build_root).output_names
            )
    runner = Runner(runtime_source_path)
    runner.toolchains = {language_for(b.language): registrations().get(b.language, {}) for b in blocks}
    for language in {f.language for f in functions} - {"python"}:
        runner.prepare_worker(language, worker_source(language, [f for f in functions if f.language == language], functions))


class Runner:
    def __init__(self, source_path: Path, build_root: Path | None = None) -> None:
        self.source_path = source_path.resolve()
        self.build_root = (build_root or self.source_path.parent / ".conflate" / "build").resolve()
        self.environment: dict[str, Any] = {"__name__": "__conflate__"}
        self.state: dict[str, Any] = {}
        self.calls = None
        self.toolchains = {}

    def run(self) -> None:
        blocks, functions = prepare_program(parse_program(self.source_path.read_text(encoding="utf-8"), str(self.source_path)))
        self.build_root.mkdir(parents=True, exist_ok=True)
        self.toolchains = {language_for(b.language): registrations().get(b.language, {}) for b in blocks}
        self.calls = Calls(self, functions) if functions else None
        try:
            for index, block in enumerate(blocks, start=1):
                language = language_for(block.language)
                if self.calls:
                    self.calls.activate(index)
                if language == "python":
                    self._run_python(block)
                elif language == "external":
                    self._run_external(block, index)
                else:
                    block = Block(block.language, decorate(block.source, language, functions), block.start_line)
                    if language == "cpp":
                        self._run_cpp(block, index)
                    else:
                        self._run_foreign(language, block, index)
        except (ValueError, BackendError) as error:
            raise ConflateError(str(error)) from error
        finally:
            if self.calls:
                self.calls.close()

    def prepare_worker(self, language, source):
        active_toolchain.set(self.toolchains.get(language, {}))
        if language == "cpp":
            executable, _, _ = _ensure_cpp_executable(Block("cpp", source, 1), 0, set(), self.source_path, self.build_root)
            return [str(executable)]
        return _ensure_foreign_artifact(language, Block(language, source, 1), 0, set(), self.build_root).command

    def _run_external(self, block, index):
        entry = registrations()[block.language]
        directory = self.build_root / ("external-" + str(index) + "-" + hashlib.sha256((block.source + json.dumps(entry)).encode()).hexdigest()[:16])
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / ("block" + entry["extension"])
        source.write_text(entry.get("template", "{source}").replace("{source}", block.source), encoding="utf-8")
        output = directory / ("block.exe" if os.name == "nt" else "block")
        state = directory / "state.json"
        substitutions = {"source": str(source), "output": str(output), "state": str(state)}
        self.calls.write(state, self.state) if self.calls else state.write_text(json.dumps(self.state), encoding="utf-8")
        for command in ([entry["compile"]] if entry.get("compile") and not output.exists() else []) + [entry["run"]]:
            result = subprocess.run([part.format_map(substitutions) for part in command], env=self.calls.environment() if self.calls else None)
            if result.returncode:
                raise ConflateError(f"@{block.language} command failed with exit code {result.returncode}")
        self.state = json.loads(state.read_text(encoding="utf-8"))
        if not isinstance(self.state, dict):
            raise ConflateError("external language shared state must be an object")

    def _run_python(self, block: Block) -> None:
        self.environment.update(self.state)
        padded = "\n" * (block.start_line - 1) + block.source
        try:
            code = compile(padded, str(self.source_path), "exec")
            exec(code, self.environment, self.environment)
        except Exception as error:
            raise ConflateError(f"Python block failed: {error}") from error
        self.state = _snapshot_python_environment(self.environment)
        if self.calls:
            self.calls.python_updates.clear()

    def _run_cpp(self, block: Block, index: int) -> None:
        executable, state_path, _ = _ensure_cpp_executable(
            block, index, set(self.state), self.source_path, self.build_root
        )
        state_path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run([str(executable), str(state_path)], env=self.calls.environment() if self.calls else None)
        if result.returncode:
            raise ConflateError(f"C++ block failed with exit code {result.returncode}")
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConflateError(f"C++ block produced invalid shared state: {error}") from error
        if not isinstance(loaded, dict):
            raise ConflateError("C++ block shared state must be an object")
        self.state = loaded
        if self.calls:
            self.state.update(self.calls.python_updates)
            self.calls.python_updates.clear()

    def _run_foreign(self, language: str, block: Block, index: int) -> None:
        artifact = _ensure_foreign_artifact(
            language, block, index, set(self.state), self.build_root
        )
        artifact.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False), encoding="utf-8"
        )
        result = subprocess.run([*artifact.command, str(artifact.state_path)], env=self.calls.environment() if self.calls else None)
        if result.returncode:
            raise ConflateError(f"{language.title()} block failed with exit code {result.returncode}")
        try:
            loaded = json.loads(artifact.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConflateError(f"{language.title()} block produced invalid shared state: {error}") from error
        if not isinstance(loaded, dict):
            raise ConflateError(f"{language.title()} block shared state must be an object")
        self.state = loaded
        if self.calls:
            self.state.update(self.calls.python_updates)
            self.calls.python_updates.clear()


def check_file(source_path: Path) -> list[Block]:
    blocks = parse_program(source_path.read_text(encoding="utf-8"), str(source_path.resolve()))
    for block in blocks:
        if block.language in {"python", "py"}:
            padded = "\n" * (block.start_line - 1) + block.source
            try:
                ast.parse(padded, filename=str(source_path.resolve()))
            except SyntaxError as error:
                raise ConflateError(f"Python syntax error: {error}") from error
    return blocks


def compile_executable(source_path: Path, output_path: Path, *, force: bool = False) -> Path:
    """Compile a Conflate source snapshot into a native launcher executable."""
    source_path = source_path.resolve()
    output_path = output_path.resolve()
    source = source_path.read_text(encoding="utf-8")
    parse_program(source, str(source_path))

    if output_path.exists() and not force:
        raise ConflateError(f"output already exists: {output_path} (use --force to replace it)")

    compiler = _cpp_compiler()

    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    delimiter = f"CFL{digest[:12]}"
    for offset in range(1, len(digest) - 11):
        if f"){delimiter}\"" not in source:
            break
        delimiter = f"CFL{digest[offset:offset + 12]}"
    else:
        raise ConflateError("could not safely embed this source file")
    python_executable = _cpp_string(sys.executable)
    temporary_name = _cpp_string(f"conflate-{digest[:12]}.confl")
    launcher = f'''#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

int main() {{
    const std::string source = R"{delimiter}({source}){delimiter}";
    const auto temporary = std::filesystem::temp_directory_path() / {temporary_name};
    {{
        std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
        if (!output) {{
            std::cerr << "conflate: could not create temporary source file\\n";
            return 2;
        }}
        output << source;
    }}
    const std::string python = {python_executable};
    #ifdef _WIN32
    const std::string command = "\\\"\\\"" + python + "\\\" -m conflate --execute-source \\\"" + temporary.string() + "\\\"\\\"";
    #else
    const std::string command = "\\\"" + python + "\\\" -m conflate --execute-source \\\"" + temporary.string() + "\\\"";
    #endif
    const int result = std::system(command.c_str());
    std::error_code ignored;
    std::filesystem::remove(temporary, ignored);
    return result;
}}
'''

    build_root = source_path.parent / ".conflate" / "build" / "launchers"
    build_root.mkdir(parents=True, exist_ok=True)
    generated_path = build_root / f"{output_path.stem}-{digest[:16]}.cpp"
    temporary_output = build_root / (f"{output_path.stem}-{digest[:16]}.exe" if os.name == "nt" else f"{output_path.stem}-{digest[:16]}")
    generated_path.write_text(launcher, encoding="utf-8")
    result = subprocess.run(
        [compiler, "-std=c++17", "-O2", str(generated_path), "-o", str(temporary_output)],
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise ConflateError(f"launcher compilation failed with exit code {result.returncode}")
    runtime_source_path = Path(tempfile.gettempdir()) / f"conflate-{digest[:12]}.confl"
    _precompile_native_blocks(source, runtime_source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    shutil.copy2(temporary_output, output_path)
    return output_path

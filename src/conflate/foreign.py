from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class BackendError(Exception):
    pass


@dataclass(frozen=True)
class Artifact:
    command: list[str]
    state_path: Path
    output_names: list[str]


JAVA_DECLARATION = re.compile(
    r"(?m)^(?:final\s+)?(?:byte|short|int|long|float|double|boolean|char|String|Object|var|"
    r"List(?:<[^;=]+>)?|Map(?:<[^;=]+>)?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|;)"
)
GO_VAR = re.compile(r"(?m)^var\s+([A-Za-z_][A-Za-z0-9_]*)\b")
GO_SHORT = re.compile(r"(?m)^([A-Za-z_][A-Za-z0-9_]*)\s*:=")
RUST_DECLARATION = re.compile(
    r"(?m)^let\s+(?:mut\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=;]+)?\s*(?:=|;)"
)


JAVA_RUNTIME = r'''
    static final class Json {
        static Map<String, Object> read(String path) throws IOException {
            Object value = new Parser(Files.readString(Path.of(path), StandardCharsets.UTF_8)).parse();
            if (!(value instanceof Map<?, ?> map)) throw new IOException("shared state is not an object");
            @SuppressWarnings("unchecked")
            Map<String, Object> result = (Map<String, Object>) map;
            return result;
        }

        static void write(String path, Map<String, Object> state) throws IOException {
            Files.writeString(Path.of(path), stringify(state), StandardCharsets.UTF_8);
        }

        static String stringify(Object value) {
            if (value == null) return "null";
            if (value instanceof Boolean || value instanceof Number) return value.toString();
            if (value instanceof Character character) return quote(character.toString());
            if (value instanceof String string) return quote(string);
            if (value instanceof Map<?, ?> map) {
                StringBuilder output = new StringBuilder("{");
                boolean first = true;
                for (Map.Entry<?, ?> entry : map.entrySet()) {
                    if (!(entry.getKey() instanceof String)) {
                        throw new IllegalArgumentException("shared map keys must be strings");
                    }
                    if (!first) output.append(',');
                    first = false;
                    output.append(quote((String) entry.getKey())).append(':').append(stringify(entry.getValue()));
                }
                return output.append('}').toString();
            }
            if (value instanceof Iterable<?> iterable) {
                StringBuilder output = new StringBuilder("[");
                boolean first = true;
                for (Object item : iterable) {
                    if (!first) output.append(',');
                    first = false;
                    output.append(stringify(item));
                }
                return output.append(']').toString();
            }
            if (value.getClass().isArray()) {
                StringBuilder output = new StringBuilder("[");
                for (int index = 0; index < Array.getLength(value); index++) {
                    if (index > 0) output.append(',');
                    output.append(stringify(Array.get(value, index)));
                }
                return output.append(']').toString();
            }
            throw new IllegalArgumentException("cannot share Java value of type " + value.getClass().getName());
        }

        static String quote(String value) {
            StringBuilder output = new StringBuilder("\"");
            for (char character : value.toCharArray()) {
                switch (character) {
                    case '"' -> output.append("\\\"");
                    case '\\' -> output.append("\\\\");
                    case '\b' -> output.append("\\b");
                    case '\f' -> output.append("\\f");
                    case '\n' -> output.append("\\n");
                    case '\r' -> output.append("\\r");
                    case '\t' -> output.append("\\t");
                    default -> {
                        if (character < 0x20) output.append(String.format("\\u%04x", (int) character));
                        else output.append(character);
                    }
                }
            }
            return output.append('"').toString();
        }

        static final class Parser {
            private final String text;
            private int position;

            Parser(String text) { this.text = text; }

            Object parse() {
                Object value = value();
                space();
                if (position != text.length()) fail("trailing data");
                return value;
            }

            Object value() {
                space();
                if (position >= text.length()) return fail("expected value");
                return switch (text.charAt(position)) {
                    case '"' -> string();
                    case '[' -> array();
                    case '{' -> object();
                    case 't' -> literal("true", true);
                    case 'f' -> literal("false", false);
                    case 'n' -> literal("null", null);
                    default -> number();
                };
            }

            Object literal(String token, Object value) {
                if (!text.startsWith(token, position)) return fail("expected " + token);
                position += token.length();
                return value;
            }

            Object number() {
                int start = position;
                if (peek('-')) position++;
                while (position < text.length() && Character.isDigit(text.charAt(position))) position++;
                boolean decimal = false;
                if (peek('.')) {
                    decimal = true;
                    position++;
                    while (position < text.length() && Character.isDigit(text.charAt(position))) position++;
                }
                if (peek('e') || peek('E')) {
                    decimal = true;
                    position++;
                    if (peek('+') || peek('-')) position++;
                    while (position < text.length() && Character.isDigit(text.charAt(position))) position++;
                }
                try {
                    String token = text.substring(start, position);
                    if (decimal) return Double.parseDouble(token);
                    return Long.parseLong(token);
                } catch (RuntimeException error) {
                    return fail("invalid number");
                }
            }

            String string() {
                expect('"');
                StringBuilder output = new StringBuilder();
                while (position < text.length()) {
                    char character = text.charAt(position++);
                    if (character == '"') return output.toString();
                    if (character != '\\') {
                        output.append(character);
                        continue;
                    }
                    if (position >= text.length()) fail("unfinished escape");
                    char escape = text.charAt(position++);
                    switch (escape) {
                        case '"', '\\', '/' -> output.append(escape);
                        case 'b' -> output.append('\b');
                        case 'f' -> output.append('\f');
                        case 'n' -> output.append('\n');
                        case 'r' -> output.append('\r');
                        case 't' -> output.append('\t');
                        case 'u' -> {
                            if (position + 4 > text.length()) fail("unfinished unicode escape");
                            output.append((char) Integer.parseInt(text.substring(position, position + 4), 16));
                            position += 4;
                        }
                        default -> fail("invalid escape");
                    }
                }
                return fail("unfinished string");
            }

            List<Object> array() {
                expect('[');
                List<Object> output = new ArrayList<>();
                space();
                if (peek(']')) { position++; return output; }
                while (true) {
                    output.add(value());
                    space();
                    if (peek(']')) { position++; return output; }
                    expect(',');
                }
            }

            Map<String, Object> object() {
                expect('{');
                Map<String, Object> output = new LinkedHashMap<>();
                space();
                if (peek('}')) { position++; return output; }
                while (true) {
                    String key = string();
                    expect(':');
                    output.put(key, value());
                    space();
                    if (peek('}')) { position++; return output; }
                    expect(',');
                }
            }

            void expect(char wanted) {
                space();
                if (position >= text.length() || text.charAt(position++) != wanted) fail("expected " + wanted);
            }

            boolean peek(char wanted) {
                return position < text.length() && text.charAt(position) == wanted;
            }

            void space() {
                while (position < text.length() && Character.isWhitespace(text.charAt(position))) position++;
            }

            <T> T fail(String message) {
                throw new IllegalArgumentException("invalid shared state at byte " + position + ": " + message);
            }
        }
    }
'''


def _tool(name: str, language: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise BackendError(f"{language} toolchain not found; install `{name}` and put it on PATH")
    return executable


def _compile(command: list[str], language: str) -> None:
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise BackendError(f"{language} compilation failed with exit code {result.returncode}")


def _artifact_dir(build_root: Path, language: str, index: int, source: str) -> tuple[Path, str]:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    directory = build_root / f"{language}-{index}-{digest}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory, digest


def _java_source(body: str, state_names: set[str]) -> tuple[str, list[str]]:
    imports: list[str] = []
    body_lines: list[str] = []
    for line in body.splitlines(keepends=True):
        if re.match(r"^\s*import\s+[A-Za-z_][A-Za-z0-9_.*]*\s*;\s*$", line):
            imports.append(line.strip())
            body_lines.append("\n" if line.endswith("\n") else "")
        else:
            body_lines.append(line)
    body = "".join(body_lines)
    declarations = set(JAVA_DECLARATION.findall(body))
    names = sorted(state_names | declarations)
    bindings = "\n".join(
        f'        Object {name} = _conflateState.get("{name}");'
        for name in sorted(state_names - declarations)
    )
    writes = "\n".join(
        f'        _conflateState.put("{name}", {name});' for name in names
    )
    source = f'''import java.io.*;
import java.lang.reflect.Array;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
{os.linesep.join(imports)}

public final class ConflateBlock {{
{JAVA_RUNTIME}

    static long conflateInt(Object value) {{ return ((Number) value).longValue(); }}
    static double conflateFloat(Object value) {{ return ((Number) value).doubleValue(); }}
    static String conflateString(Object value) {{ return (String) value; }}
    @SuppressWarnings("unchecked")
    static List<Object> conflateList(Object value) {{ return (List<Object>) value; }}

    public static void main(String[] args) throws Exception {{
        if (args.length != 1) throw new IllegalArgumentException("missing state file");
        Map<String, Object> _conflateState = Json.read(args[0]);
{bindings}
{body}
{writes}
        Json.write(args[0], _conflateState);
    }}
}}
'''
    return source, names


def ensure_java(
    body: str,
    index: int,
    state_names: set[str],
    build_root: Path,
) -> Artifact:
    source, names = _java_source(body, state_names)
    directory, _ = _artifact_dir(build_root, "java", index, source)
    source_path = directory / "ConflateBlock.java"
    class_path = directory / "ConflateBlock.class"
    if not class_path.exists():
        source_path.write_text(source, encoding="utf-8")
        _compile([_tool("javac", "Java"), "-encoding", "UTF-8", "-d", str(directory), str(source_path)], "Java")
    return Artifact(
        [_tool("java", "Java"), "-cp", str(directory), "ConflateBlock"],
        directory / "state.json",
        names,
    )


GO_IMPORTS = {
    "bufio": "bufio",
    "fmt": "fmt",
    "math": "math",
    "strconv": "strconv",
    "strings": "strings",
    "time": "time",
}


def _go_source(body: str, state_names: set[str]) -> tuple[str, list[str]]:
    explicit_imports: list[tuple[str | None, str]] = []
    body_lines: list[str] = []
    import_pattern = re.compile(
        r'^\s*import\s+(?:(?P<alias>[A-Za-z_][A-Za-z0-9_]*|[._])\s+)?"(?P<path>[^"]+)"\s*$'
    )
    for line in body.splitlines(keepends=True):
        match = import_pattern.match(line.rstrip("\r\n"))
        if match:
            explicit_imports.append((match.group("alias"), match.group("path")))
            body_lines.append("\n" if line.endswith("\n") else "")
        else:
            body_lines.append(line)
    body = "".join(body_lines)
    declarations = set(GO_VAR.findall(body)) | set(GO_SHORT.findall(body))
    declarations.discard("_")
    names = sorted(state_names | declarations)
    explicit_paths = {path for _, path in explicit_imports}
    user_imports = [
        (None, path)
        for qualifier, path in GO_IMPORTS.items()
        if path not in explicit_paths and re.search(rf"\b{qualifier}\s*\.", body)
    ]
    imports = "\n".join(
        f'    {(alias + " ") if alias else ""}"{path}"'
        for alias, path in [*explicit_imports, *user_imports]
    )
    bindings = "\n".join(
        f'    var {name} any = _conflateState["{name}"]'
        for name in sorted(state_names - declarations)
    )
    writes = "\n".join(
        f'    _conflateState["{name}"] = {name}' for name in names
    )
    source = f'''package main

import (
    "encoding/json"
    "os"
{imports}
)

func conflateInt(value any) int64 {{ return int64(value.(float64)) }}
func conflateFloat(value any) float64 {{ return value.(float64) }}
func conflateString(value any) string {{ return value.(string) }}
func conflateList(value any) []any {{ return value.([]any) }}

func main() {{
    _conflateBytes, err := os.ReadFile(os.Args[1])
    if err != nil {{ panic(err) }}
    _conflateState := map[string]any{{}}
    if err := json.Unmarshal(_conflateBytes, &_conflateState); err != nil {{ panic(err) }}
{bindings}
{body}
{writes}
    _conflateBytes, err = json.Marshal(_conflateState)
    if err != nil {{ panic(err) }}
    if err := os.WriteFile(os.Args[1], _conflateBytes, 0644); err != nil {{ panic(err) }}
}}
'''
    return source, names


def ensure_go(
    body: str,
    index: int,
    state_names: set[str],
    build_root: Path,
) -> Artifact:
    source, names = _go_source(body, state_names)
    directory, _ = _artifact_dir(build_root, "go", index, source)
    source_path = directory / "block.go"
    executable = directory / ("block.exe" if os.name == "nt" else "block")
    if not executable.exists():
        source_path.write_text(source, encoding="utf-8")
        _compile([_tool("go", "Go"), "build", "-o", str(executable), str(source_path)], "Go")
    return Artifact([str(executable)], directory / "state.json", names)


RUST_RUNTIME = r'''
#[derive(Clone, Debug)]
enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    String(String),
    Array(Vec<Value>),
    Object(BTreeMap<String, Value>),
}

macro_rules! from_int {
    ($($kind:ty),*) => {$(
        impl From<$kind> for Value {
            fn from(value: $kind) -> Self { Value::Int(value as i64) }
        }
    )*};
}
from_int!(i8, i16, i32, i64, isize, u8, u16, u32, u64, usize);

impl From<bool> for Value { fn from(value: bool) -> Self { Value::Bool(value) } }
impl From<f32> for Value { fn from(value: f32) -> Self { Value::Float(value as f64) } }
impl From<f64> for Value { fn from(value: f64) -> Self { Value::Float(value) } }
impl From<String> for Value { fn from(value: String) -> Self { Value::String(value) } }
impl From<&str> for Value { fn from(value: &str) -> Self { Value::String(value.to_owned()) } }
impl<T: Into<Value>> From<Vec<T>> for Value {
    fn from(value: Vec<T>) -> Self { Value::Array(value.into_iter().map(Into::into).collect()) }
}

impl Value {
    fn as_i64(&self) -> Result<i64, String> {
        match self {
            Value::Int(value) => Ok(*value),
            _ => Err("shared value is not an integer".to_owned()),
        }
    }

    fn as_f64(&self) -> Result<f64, String> {
        match self {
            Value::Int(value) => Ok(*value as f64),
            Value::Float(value) => Ok(*value),
            _ => Err("shared value is not a number".to_owned()),
        }
    }

    fn as_str(&self) -> Result<&str, String> {
        match self {
            Value::String(value) => Ok(value),
            _ => Err("shared value is not a string".to_owned()),
        }
    }

    fn json(&self) -> String {
        match self {
            Value::Null => "null".to_owned(),
            Value::Bool(value) => value.to_string(),
            Value::Int(value) => value.to_string(),
            Value::Float(value) => value.to_string(),
            Value::String(value) => quote(value),
            Value::Array(values) => format!("[{}]", values.iter().map(Value::json).collect::<Vec<_>>().join(",")),
            Value::Object(values) => format!(
                "{{{}}}",
                values.iter().map(|(key, value)| format!("{}:{}", quote(key), value.json())).collect::<Vec<_>>().join(",")
            ),
        }
    }

    fn display(&self, output: &mut fmt::Formatter<'_>, nested: bool) -> fmt::Result {
        match self {
            Value::Null => write!(output, "None"),
            Value::Bool(value) => write!(output, "{value}"),
            Value::Int(value) => write!(output, "{value}"),
            Value::Float(value) => write!(output, "{value}"),
            Value::String(value) if nested => write!(output, "\"{value}\""),
            Value::String(value) => write!(output, "{value}"),
            Value::Array(values) => {
                write!(output, "[")?;
                for (index, value) in values.iter().enumerate() {
                    if index > 0 { write!(output, ", ")?; }
                    value.display(output, true)?;
                }
                write!(output, "]")
            }
            Value::Object(values) => {
                write!(output, "{{")?;
                for (index, (key, value)) in values.iter().enumerate() {
                    if index > 0 { write!(output, ", ")?; }
                    write!(output, "\"{key}\": ")?;
                    value.display(output, true)?;
                }
                write!(output, "}}")
            }
        }
    }
}

impl fmt::Display for Value {
    fn fmt(&self, output: &mut fmt::Formatter<'_>) -> fmt::Result { self.display(output, false) }
}

fn quote(value: &str) -> String {
    let mut output = String::from("\"");
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\u{08}' => output.push_str("\\b"),
            '\u{0c}' => output.push_str("\\f"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            value if value < '\u{20}' => output.push_str(&format!("\\u{:04x}", value as u32)),
            value => output.push(value),
        }
    }
    output.push('"');
    output
}

struct Parser<'a> {
    text: &'a str,
    position: usize,
}

impl<'a> Parser<'a> {
    fn new(text: &'a str) -> Self { Self { text, position: 0 } }

    fn parse(mut self) -> Result<Value, String> {
        let value = self.value()?;
        self.space();
        if self.position != self.text.len() { return self.fail("trailing data"); }
        Ok(value)
    }

    fn fail<T>(&self, message: &str) -> Result<T, String> {
        Err(format!("invalid shared state at byte {}: {}", self.position, message))
    }

    fn bytes(&self) -> &[u8] { self.text.as_bytes() }

    fn space(&mut self) {
        while self.position < self.text.len() && self.bytes()[self.position].is_ascii_whitespace() {
            self.position += 1;
        }
    }

    fn consume(&mut self, token: &str) -> bool {
        self.space();
        if self.text[self.position..].starts_with(token) {
            self.position += token.len();
            true
        } else {
            false
        }
    }

    fn expect(&mut self, wanted: u8) -> Result<(), String> {
        self.space();
        if self.position >= self.text.len() || self.bytes()[self.position] != wanted {
            return self.fail("unexpected character");
        }
        self.position += 1;
        Ok(())
    }

    fn value(&mut self) -> Result<Value, String> {
        self.space();
        if self.position >= self.text.len() { return self.fail("expected value"); }
        match self.bytes()[self.position] {
            b'"' => self.string().map(Value::String),
            b'[' => self.array(),
            b'{' => self.object(),
            b't' if self.consume("true") => Ok(Value::Bool(true)),
            b'f' if self.consume("false") => Ok(Value::Bool(false)),
            b'n' if self.consume("null") => Ok(Value::Null),
            b'-' | b'0'..=b'9' => self.number(),
            _ => self.fail("expected value"),
        }
    }

    fn number(&mut self) -> Result<Value, String> {
        self.space();
        let start = self.position;
        if self.bytes()[self.position] == b'-' { self.position += 1; }
        while self.position < self.text.len() && self.bytes()[self.position].is_ascii_digit() { self.position += 1; }
        let mut float = false;
        if self.position < self.text.len() && self.bytes()[self.position] == b'.' {
            float = true;
            self.position += 1;
            while self.position < self.text.len() && self.bytes()[self.position].is_ascii_digit() { self.position += 1; }
        }
        if self.position < self.text.len() && matches!(self.bytes()[self.position], b'e' | b'E') {
            float = true;
            self.position += 1;
            if self.position < self.text.len() && matches!(self.bytes()[self.position], b'+' | b'-') { self.position += 1; }
            while self.position < self.text.len() && self.bytes()[self.position].is_ascii_digit() { self.position += 1; }
        }
        let token = &self.text[start..self.position];
        if float {
            token.parse::<f64>().map(Value::Float).map_err(|_| "invalid shared number".to_owned())
        } else {
            token.parse::<i64>().map(Value::Int).map_err(|_| "invalid shared number".to_owned())
        }
    }

    fn string(&mut self) -> Result<String, String> {
        self.expect(b'"')?;
        let mut output = String::new();
        while self.position < self.text.len() {
            let byte = self.bytes()[self.position];
            self.position += 1;
            match byte {
                b'"' => return Ok(output),
                b'\\' => {
                    if self.position >= self.text.len() { return self.fail("unfinished escape"); }
                    let escape = self.bytes()[self.position];
                    self.position += 1;
                    match escape {
                        b'"' => output.push('"'),
                        b'\\' => output.push('\\'),
                        b'/' => output.push('/'),
                        b'b' => output.push('\u{08}'),
                        b'f' => output.push('\u{0c}'),
                        b'n' => output.push('\n'),
                        b'r' => output.push('\r'),
                        b't' => output.push('\t'),
                        b'u' => {
                            if self.position + 4 > self.text.len() { return self.fail("unfinished unicode escape"); }
                            let code = u32::from_str_radix(&self.text[self.position..self.position + 4], 16)
                                .map_err(|_| "invalid unicode escape".to_owned())?;
                            self.position += 4;
                            output.push(char::from_u32(code).ok_or_else(|| "invalid unicode codepoint".to_owned())?);
                        }
                        _ => return self.fail("invalid escape"),
                    }
                }
                value if value.is_ascii() => output.push(value as char),
                _ => {
                    self.position -= 1;
                    let character = self.text[self.position..].chars().next().ok_or_else(|| "invalid utf-8".to_owned())?;
                    self.position += character.len_utf8();
                    output.push(character);
                }
            }
        }
        self.fail("unfinished string")
    }

    fn array(&mut self) -> Result<Value, String> {
        self.expect(b'[')?;
        let mut output = Vec::new();
        self.space();
        if self.position < self.text.len() && self.bytes()[self.position] == b']' {
            self.position += 1;
            return Ok(Value::Array(output));
        }
        loop {
            output.push(self.value()?);
            self.space();
            if self.position < self.text.len() && self.bytes()[self.position] == b']' {
                self.position += 1;
                return Ok(Value::Array(output));
            }
            self.expect(b',')?;
        }
    }

    fn object(&mut self) -> Result<Value, String> {
        self.expect(b'{')?;
        let mut output = BTreeMap::new();
        self.space();
        if self.position < self.text.len() && self.bytes()[self.position] == b'}' {
            self.position += 1;
            return Ok(Value::Object(output));
        }
        loop {
            let key = self.string()?;
            self.expect(b':')?;
            output.insert(key, self.value()?);
            self.space();
            if self.position < self.text.len() && self.bytes()[self.position] == b'}' {
                self.position += 1;
                return Ok(Value::Object(output));
            }
            self.expect(b',')?;
        }
    }
}

fn read_state(path: &str) -> Result<BTreeMap<String, Value>, String> {
    match Parser::new(&fs::read_to_string(path).map_err(|error| error.to_string())?).parse()? {
        Value::Object(state) => Ok(state),
        _ => Err("shared state is not an object".to_owned()),
    }
}

fn write_state(path: &str, state: &BTreeMap<String, Value>) -> Result<(), String> {
    fs::write(path, Value::Object(state.clone()).json()).map_err(|error| error.to_string())
}
'''


def _rust_source(body: str, state_names: set[str]) -> tuple[str, list[str]]:
    declarations = set(RUST_DECLARATION.findall(body))
    names = sorted(state_names | declarations)
    bindings = "\n".join(
        f'    let mut {name} = _conflate_state.remove("{name}").unwrap_or(Value::Null);'
        for name in sorted(state_names - declarations)
    )
    writes = "\n".join(
        f'    _conflate_state.insert("{name}".to_owned(), Value::from({name}));' for name in names
    )
    source = f'''use std::collections::BTreeMap;
use std::fmt;
use std::fs;

{RUST_RUNTIME}

fn main() -> Result<(), String> {{
    let path = std::env::args().nth(1).ok_or_else(|| "missing state file".to_owned())?;
    let mut _conflate_state = read_state(&path)?;
{bindings}
{body}
{writes}
    write_state(&path, &_conflate_state)?;
    Ok(())
}}
'''
    return source, names


def ensure_rust(
    body: str,
    index: int,
    state_names: set[str],
    build_root: Path,
) -> Artifact:
    source, names = _rust_source(body, state_names)
    directory, _ = _artifact_dir(build_root, "rust", index, source)
    source_path = directory / "block.rs"
    executable = directory / ("block.exe" if os.name == "nt" else "block")
    if not executable.exists():
        source_path.write_text(source, encoding="utf-8")
        _compile(
            [_tool("rustc", "Rust"), "--edition=2021", "-C", "opt-level=0", str(source_path), "-o", str(executable)],
            "Rust",
        )
    return Artifact([str(executable)], directory / "state.json", names)

"""Persistent function workers and generated native call wrappers."""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


GLOBALS = "// conflate generated globals\n"
BODY = "// conflate generated body\n"


def split_globals(source):
    if source.startswith(GLOBALS):
        return source[len(GLOBALS):].split(BODY, 1)
    return "", source


@dataclass
class Function:
    name: str
    language: str
    parameters: list[tuple[str, str]]
    returns: str
    source: str
    block: int


def masked(source):
    # Keep offsets while hiding braces in ordinary comments and strings.
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`[^`]*`'
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m[0]), source)


def extract(source, language, block):
    if language == "python":
        tree = ast.parse(source)
        functions = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                parameters = [(a.arg, "") for a in [*node.args.posonlyargs, *node.args.args]]
                functions.append(Function(node.name, language, parameters, "", "", block))
        return source, functions
    patterns = {
        "cpp": r"(?m)^(?:inline\s+)?(?P<ret>[\w:<>]+(?:\s+long)?)\s+(?P<name>\w+)\s*\((?P<args>[^{};]*)\)\s*\{",
        "java": r"(?m)^(?:(?:public|private|protected|static|final)\s+)*(?P<ret>[\w<>\[\]]+)\s+(?P<name>\w+)\s*\((?P<args>[^{};]*)\)(?:\s+throws\s+[\w., ]+)?\s*\{",
        "go": r"(?m)^func\s+(?P<name>\w+)\s*\((?P<args>[^{}]*)\)\s*(?P<ret>[\w\[\]]*)\s*\{",
        "rust": r"(?m)^(?:pub\s+)?fn\s+(?P<name>\w+)\s*\((?P<args>[^{}]*)\)\s*(?:->\s*(?P<ret>[^{}]+?))?\s*\{",
        "javascript": r"(?m)^function\s+(?P<name>\w+)\s*\((?P<args>[^{}]*)\)(?P<ret>)\s*\{",
    }
    if language not in patterns:
        return source, []
    hidden = masked(source)
    functions, edits = [], []
    end = 0
    for match in re.finditer(patterns[language], hidden):
        if match.start() < end:
            continue
        depth, end = 1, match.end()
        while depth and end < len(hidden):
            depth += (hidden[end] == "{") - (hidden[end] == "}")
            end += 1
        if depth:
            raise ValueError(f"unclosed function {match['name']}")
        parameters = []
        args = match["args"].strip()
        if args and args != "void":
            for argument in args.split(","):
                if language == "javascript":
                    name, kind = argument.strip(), "any"
                elif language == "rust":
                    name, kind = argument.strip().split(":", 1)
                    name = name.removeprefix("mut ")
                elif language == "go":
                    name, kind = argument.strip().split(None, 1)
                else:
                    kind, name = argument.strip().rsplit(None, 1)
                if not re.fullmatch(r"[A-Za-z_]\w*", name.strip()):
                    raise ValueError(f"unsupported parameter in {match['name']}: {argument}")
                parameters.append((name.strip(), kind.strip()))
        definition = source[match.start():end]
        if language == "java" and not re.match(r"(?:public\s+|private\s+|protected\s+)*static\b", definition):
            definition = "static " + definition
        functions.append(Function(match["name"], language, parameters, (match["ret"] or "void").strip(), definition, block))
        edits.append((match.start(), end))
    for start, end in reversed(edits):
        source = source[:start] + "\n" * source[start:end].count("\n") + source[end:]
    return source, functions


CPP_BRIDGE = r'''
#include <filesystem>
#include <thread>
#include <chrono>
#include <atomic>
#include <cstdlib>
inline void cfl_write(const std::string& path, const conflate::Value& value) {
    { std::ofstream stream(path + ".tmp"); conflate::write_json(stream, value); }
    std::filesystem::rename(path + ".tmp", path);
}
inline conflate::Value cfl_call(const std::string& name, conflate::Value::array_t args) {
    static std::atomic<unsigned long> sequence{0};
    const auto base = std::string(std::getenv("CONFLATE_CALLS")) + "/" +
        std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + "-" + std::to_string(sequence++);
    cfl_write(base + ".request", conflate::Value::object_t{{"name",name},{"args",args}});
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(60);
    while (!std::filesystem::exists(base + ".response")) {
        if (std::chrono::steady_clock::now() > deadline) throw std::runtime_error("function call timed out: " + name);
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    auto result = conflate::read_state((base + ".response").c_str());
    std::filesystem::remove(base + ".response");
    if (result.count("error")) throw std::runtime_error(result.at("error").as<std::string>());
    return result.at("result");
}
'''

JAVA_BRIDGE = r'''
    static void cflWrite(String path, Object value) throws Exception {
        Files.writeString(Path.of(path + ".tmp"), Json.stringify(value));
        Files.move(Path.of(path + ".tmp"), Path.of(path), StandardCopyOption.REPLACE_EXISTING);
    }
    static Object cflCall(String name, Object... arguments) throws Exception {
        String base = System.getenv("CONFLATE_CALLS") + "/" + UUID.randomUUID();
        cflWrite(base + ".request", Map.of("name", name, "args", Arrays.asList(arguments)));
        long deadline = System.nanoTime() + 60_000_000_000L;
        while (!Files.exists(Path.of(base + ".response"))) {
            if (System.nanoTime() > deadline) throw new IOException("function call timed out: " + name);
            Thread.sleep(1);
        }
        Map<String,Object> response = Json.read(base + ".response");
        Files.delete(Path.of(base + ".response"));
        if (response.containsKey("error")) throw new IOException(response.get("error").toString());
        return response.get("result");
    }
'''

GO_BRIDGE = r'''
func cflWrite(path string, value any) {
    data, err := json.Marshal(value); if err != nil { panic(err) }
    if err := os.WriteFile(path+".tmp", data, 0600); err != nil { panic(err) }
    if err := os.Rename(path+".tmp", path); err != nil { panic(err) }
}
func cflRead(path string) map[string]any {
    data, err := os.ReadFile(path); if err != nil { panic(err) }
    var value map[string]any
    if err := json.Unmarshal(data, &value); err != nil { panic(err) }
    return value
}
func cflCall(name string, args ...any) any {
    file, err := os.CreateTemp(os.Getenv("CONFLATE_CALLS"), "call-"); if err != nil { panic(err) }
    base := file.Name(); file.Close(); os.Remove(base)
    if args == nil { args = []any{} }
    cflWrite(base+".request", map[string]any{"name":name,"args":args})
    deadline := time.Now().Add(60*time.Second)
    for { if _,err := os.Stat(base+".response"); err == nil { break }; if time.Now().After(deadline) { panic("function call timed out: "+name) }; time.Sleep(time.Millisecond) }
    response := cflRead(base+".response"); os.Remove(base+".response")
    if err, ok := response["error"]; ok { panic(err) }
    return response["result"]
}
'''

RUST_BRIDGE = r'''
fn cfl_write(path: &str, value: &Value) -> Result<(), String> {
    fs::write(format!("{path}.tmp"), value.json()).map_err(|e| e.to_string())?;
    fs::rename(format!("{path}.tmp"), path).map_err(|e| e.to_string())
}
fn cfl_call(name: &str, args: Vec<Value>) -> Value {
    static SEQUENCE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let base = format!("{}/{}-{}", std::env::var("CONFLATE_CALLS").unwrap(), std::process::id(), SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed));
    let request = Value::Object(BTreeMap::from([("name".to_owned(),Value::from(name)),("args".to_owned(),Value::Array(args))]));
    cfl_write(&format!("{base}.request"), &request).unwrap();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(60);
    while !std::path::Path::new(&format!("{base}.response")).exists() {
        assert!(std::time::Instant::now() < deadline, "function call timed out: {name}");
        std::thread::sleep(std::time::Duration::from_millis(1));
    }
    let mut response = read_state(&format!("{base}.response")).unwrap();
    fs::remove_file(format!("{base}.response")).unwrap();
    if let Some(error) = response.remove("error") { panic!("{}", error); }
    response.remove("result").unwrap_or(Value::Null)
}
'''

JS_BRIDGE = r'''
function cflWrite(path, value) {
    fs.writeFileSync(path + '.tmp', JSON.stringify(value));
    fs.renameSync(path + '.tmp', path);
}
function cflSleep() { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 1); }
function cflCall(name, ...args) {
    const base = process.env.CONFLATE_CALLS + '/' + require('crypto').randomUUID();
    cflWrite(base + '.request', {name, args});
    const deadline = Date.now() + 60000;
    while (!fs.existsSync(base + '.response')) {
        if (Date.now() > deadline) throw new Error('function call timed out: ' + name);
        cflSleep();
    }
    const response = JSON.parse(fs.readFileSync(base + '.response', 'utf8'));
    fs.unlinkSync(base + '.response');
    if ('error' in response) throw new Error(response.error);
    return response.result;
}
'''


def wrappers(language, functions):
    output = []
    for function in functions:
        name = function.name
        if language == "cpp":
            output.append(f'template<class... A> conflate::Value {name}(A... a) {{ return cfl_call("{name}", {{conflate::Value(a)...}}); }}')
        elif language == "java":
            output.append(f'static Object {name}(Object... a) throws Exception {{ return cflCall("{name}", a); }}')
        elif language == "go":
            output.append(f'func {name}(a ...any) any {{ return cflCall("{name}", a...) }}')
        elif language == "rust":
            parameters = ", ".join(f"a{i}: impl Into<Value>" for i in range(len(function.parameters)))
            args = ", ".join(f"a{i}.into()" for i in range(len(function.parameters)))
            output.append(f'fn {name}({parameters}) -> Value {{ cfl_call("{name}", vec![{args}]) }}')
        elif language == "javascript":
            output.append(f'function {name}(...a) {{ return cflCall("{name}", ...a); }}')
    return "\n".join(output)


def bridge(language):
    return {"cpp": CPP_BRIDGE, "java": JAVA_BRIDGE, "go": GO_BRIDGE, "rust": RUST_BRIDGE, "javascript": JS_BRIDGE}[language]


def decorate(source, language, functions):
    if not functions:
        return source
    return GLOBALS + bridge(language) + wrappers(language, functions) + "\n" + BODY + source


def argument(language, kind, index):
    value = f"a[{index}]" if language != "java" else f"a.get({index})"
    if language == "javascript":
        return value
    if language == "cpp":
        return f"{value}.as<{kind}>()"
    if language == "java":
        if kind in {"int", "long", "short", "byte", "float", "double"}:
            return f"((Number){value}).{kind}Value()"
        return f"({kind}){value}"
    if language == "go":
        if kind in {"int", "int32", "int64", "uint", "uint64", "float32", "float64"}:
            return f"{kind}({value}.(float64))"
        return value if kind == "any" else f"{value}.({kind})"
    if kind in {"i8", "i16", "i32", "i64", "isize", "u8", "u16", "u32", "u64", "usize"}:
        return f"{value}.as_i64()? as {kind}"
    if kind in {"f32", "f64"}:
        return f"{value}.as_f64()? as {kind}"
    if kind in {"String", "&str"}:
        return f"{value}.as_str()?" + (".to_owned()" if kind == "String" else "")
    if kind == "bool":
        return f'match &{value} {{ Value::Bool(v) => *v, _ => return Err("expected bool".into()) }}'
    if kind == "Value":
        return f"{value}.clone()"
    raise ValueError(f"unsupported Rust function argument type: {kind}")


def worker_source(language, owned, all_functions):
    globals_source = bridge(language) + wrappers(language, [f for f in all_functions if f.language != language])
    if language == "cpp":
        globals_source += "\n" + "\n".join(f.source.split("{", 1)[0] + ";" for f in owned)
    globals_source += "\n" + "\n".join(f.source for f in owned) + "\n"
    cases = []
    for f in owned:
        call = f"{f.name}({', '.join(argument(language, kind, i) for i, (_, kind) in enumerate(f.parameters))})"
        count = len(f.parameters)
        if language == "cpp":
            result = f"{call}; return nullptr;" if f.returns == "void" else f"return conflate::Value({call});"
            cases.append(f'if (name == "{f.name}") {{ if(a.size() != {count}) throw std::runtime_error("wrong argument count for {f.name}"); {result} }}')
        elif language == "java":
            result = f"{call}; return null;" if f.returns == "void" else f"return {call};"
            cases.append(f'if (name.equals("{f.name}")) {{ if(a.size() != {count}) throw new IllegalArgumentException("wrong argument count for {f.name}"); {result} }}')
        elif language == "go":
            result = f"{call}; return nil" if f.returns == "void" else f"return {call}"
            cases.append(f'case "{f.name}": if len(a) != {count} {{ panic("wrong argument count for {f.name}") }}; {result}')
        elif language == "javascript":
            cases.append(f'case "{f.name}": if (a.length !== {count}) throw new Error("wrong argument count for {f.name}"); return {call};')
        else:
            result = f"{call}; Ok(Value::Null)" if f.returns in {"void", "()"} else f"Ok(Value::from({call}))"
            cases.append(f'"{f.name}" => {{ if a.len() != {count} {{ return Err("wrong argument count for {f.name}".into()); }} {result} }}')
    cases = "\n".join(cases)
    if language == "cpp":
        globals_source += f'conflate::Value cfl_dispatch(std::string name, conflate::Value::array_t a) {{ {cases} throw std::runtime_error("unknown function"); }}\n'
        body = r'''
    while (true) {
        const std::string request = std::string(argv[1]) + ".request";
        if (!std::filesystem::exists(request)) { std::this_thread::sleep_for(std::chrono::milliseconds(1)); continue; }
        conflate::Value::object_t response;
        try {
            auto input = conflate::read_state(request.c_str()); std::filesystem::remove(request);
            response["result"] = cfl_dispatch(input.at("name").as<std::string>(), input.at("args").as<conflate::Value::array_t>());
        } catch (const std::exception& error) { response["error"] = error.what(); }
        cfl_write(std::string(argv[1]) + ".response", response);
    }
'''
    elif language == "java":
        globals_source += f'static Object cflDispatch(String name, List<Object> a) throws Exception {{ {cases} throw new IllegalArgumentException("unknown function"); }}\n'
        body = r'''
        while (!Thread.currentThread().isInterrupted()) {
            String request = args[0] + ".request";
            if (!Files.exists(Path.of(request))) { Thread.sleep(1); continue; }
            Map<String,Object> response = new HashMap<>();
            try {
                Map<String,Object> input = Json.read(request); Files.delete(Path.of(request));
                response.put("result", cflDispatch((String)input.get("name"), conflateList(input.get("args"))));
            } catch (Exception error) { response.put("error", error.toString()); }
            cflWrite(args[0] + ".response", response);
        }
'''
    elif language == "go":
        globals_source += f'func cflDispatch(name string, a []any) any {{ switch name {{ {cases} }}; panic("unknown function") }}\n'
        body = r'''
    for {
        request := os.Args[1]+".request"
        if _,err := os.Stat(request); err != nil { time.Sleep(time.Millisecond); continue }
        response := map[string]any{}
        func() {
            defer func() { if e := recover(); e != nil { response["error"] = fmt.Sprint(e) } }()
            input := cflRead(request); os.Remove(request)
            response["result"] = cflDispatch(input["name"].(string), input["args"].([]any))
        }()
        cflWrite(os.Args[1]+".response", response)
    }
'''
    elif language == "javascript":
        globals_source += f'function cflDispatch(name, a) {{ switch(name) {{ {cases} }} throw new Error("unknown function"); }}\n'
        body = r'''
    while (true) {
        const request = process.argv[2] + '.request';
        if (!fs.existsSync(request)) { cflSleep(); continue; }
        let response;
        try {
            const input = JSON.parse(fs.readFileSync(request, 'utf8')); fs.unlinkSync(request);
            response = {result: cflDispatch(input.name, input.args) ?? null};
        } catch (error) { response = {error: String(error)}; }
        cflWrite(process.argv[2] + '.response', response);
    }
'''
    else:
        globals_source += f'fn cfl_dispatch(name: &str, a: Vec<Value>) -> Result<Value,String> {{ match name {{ {cases}, _ => Err("unknown function".into()) }} }}\n'
        body = r'''
    loop {
        let request = format!("{path}.request");
        if !std::path::Path::new(&request).exists() { std::thread::sleep(std::time::Duration::from_millis(1)); continue; }
        let outcome = std::panic::catch_unwind(|| -> Result<Value,String> {
            let mut input = read_state(&request)?; fs::remove_file(&request).map_err(|e| e.to_string())?;
            let name = input.remove("name").ok_or("missing name")?;
            let a = match input.remove("args") { Some(Value::Array(a)) => a, _ => return Err("missing arguments".into()) };
            cfl_dispatch(name.as_str()?, a)
        });
        let (key,value) = match outcome {
            Ok(Ok(value)) => ("result",value), Ok(Err(error)) => ("error",Value::from(error)),
            Err(error) => ("error", Value::from(error.downcast_ref::<String>().cloned().or_else(|| error.downcast_ref::<&str>().map(|s|s.to_string())).unwrap_or("Rust function panicked".into()))),
        };
        cfl_write(&format!("{path}.response"), &Value::Object(BTreeMap::from([(key.to_owned(),value)])))?;
    }
'''
    return GLOBALS + globals_source + BODY + body


class Calls:
    def __init__(self, runner, functions):
        self.runner, self.functions = runner, functions
        self.directory = tempfile.TemporaryDirectory(prefix="conflate-calls-")
        self.root = Path(self.directory.name)
        self.active = {}
        self.python_updates = {}
        self.workers = {}
        self.busy = set()
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def environment(self):
        import os
        return {**os.environ, "CONFLATE_CALLS": str(self.root)}

    def activate(self, block):
        for function in self.functions:
            if function.block == block:
                self.active[function.name] = function
                if function.language != "python":
                    self.runner.environment[function.name] = lambda *args, _name=function.name: self.call(_name, list(args))

    def serve(self):
        while not self.stopped.wait(0.001):
            self.pump()

    def pump(self):
        # The lock also lets a waiting caller service callbacks on this thread.
        with self.lock:
            for path in self.root.glob("*.request"):
                try:
                    request = json.loads(path.read_text(encoding="utf-8"))
                    path.unlink()
                    result = {"result": self.call(request["name"], request["args"])}
                except Exception as error:
                    result = {"error": str(error)}
                try:
                    self.write(path.with_suffix(".response"), result)
                except (TypeError, ValueError) as error:
                    self.write(path.with_suffix(".response"), {"error": f"function returned a nonportable value: {error}"})

    @staticmethod
    def write(path, value):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(path)

    def call(self, name, args):
        with self.lock:
            if name not in self.active:
                raise ValueError(f"function {name} is not defined yet")
            function = self.active[name]
            if function.language == "python":
                from .compiler import _snapshot_python_environment
                before = _snapshot_python_environment(self.runner.environment)
                try:
                    result = self.runner.environment[name](*args)
                    json.dumps(result, allow_nan=False)
                    return result
                finally:
                    after = _snapshot_python_environment(self.runner.environment)
                    self.python_updates.update({key: value for key, value in after.items() if key not in before or value != before[key]})
            language = function.language
            if language in self.busy:
                raise ValueError(f"reentrant callback into busy {language} worker is not supported")
            if language not in self.workers:
                owned = [f for f in self.functions if f.language == language]
                source = worker_source(language, owned, self.functions)
                command = self.runner.prepare_worker(language, source)
                worker_directory = self.root / language
                worker_directory.mkdir()
                state = worker_directory / "state.json"
                self.write(state, {})
                process = subprocess.Popen([*command, str(state)], env=self.environment())
                self.workers[language] = process, state
            process, state = self.workers[language]
            self.busy.add(language)
            try:
                self.write(Path(str(state) + ".request"), {"name": name, "args": args})
                response = Path(str(state) + ".response")
                deadline = time.monotonic() + 60
                while not response.exists():
                    if process.poll() is not None:
                        raise ValueError(f"{language} function worker exited with code {process.returncode}")
                    if time.monotonic() > deadline:
                        self.stop_worker(process)
                        raise ValueError(f"function {name} timed out after 60 seconds")
                    self.pump()
                    time.sleep(0.001)
                result = json.loads(response.read_text(encoding="utf-8"))
                response.unlink()
                if "error" in result:
                    raise ValueError(f"{language}.{name}: {result['error']}")
                return result["result"]
            finally:
                self.busy.remove(language)

    def close(self):
        self.stopped.set()
        for process, _ in self.workers.values():
            self.stop_worker(process)
        self.thread.join(timeout=5)
        self.directory.cleanup()

    @staticmethod
    def stop_worker(process):
        if process.poll() is None:
            if os.name == "nt":
                # Java's Windows PATH shim starts a child JVM that inherits our pipes.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

# Conflate documentation

Conflate treats one source file as a sequence of language blocks. The marker at
the start of a block chooses the language; the code below it stays ordinary code
for that language.

Version 0.2 supports Python, C++, Rust, Java, and Go.

## File format

A Conflate source file uses the `.confl` extension:

```cpp
@python
name = input("Your name: ")

@cpp
std::cout << "Hello, " << name << "!\n";
```

Accepted markers are:

| Language | Markers |
| --- | --- |
| Python | `@python`, `@py` |
| C++ | `@cpp`, `@c++` |
| Rust | `@rust`, `@rs` |
| Java | `@java` |
| Go | `@go`, `@golang` |

Code before the first marker is an error. Blocks run in file order.

For simple one-line C++ statements, the final semicolon is optional:

```cpp
@cpp
std::cout << "hello"
```

Normal C++ syntax is still recommended once a block grows beyond a line or two.

## Command line

Compile a source file:

```powershell
conflate -c program.confl
```

On Windows this creates `program.exe`. Use `-o` to choose another path:

```powershell
conflate -c program.confl -o build/my-program.exe
```

Conflate refuses to replace an existing output unless you pass `--force`:

```powershell
conflate -c program.confl --force
```

Run the compiled launcher:

```powershell
conflate -r program.exe
```

Check markers and Python syntax without running the program:

```powershell
conflate --check program.confl
```

## How execution works

The compiler splits the file into blocks and creates a shared state dictionary.
Python blocks run in one persistent Python environment. C++, Rust, Java, and Go
blocks are wrapped in generated entry points and compiled by their normal
toolchains.

Between blocks, Conflate serializes supported values as JSON. Each native backend
loads that state before its block and writes supported variables back afterward.

The generated launcher embeds a snapshot of the `.confl` source. When launched,
it uses the installed Conflate runtime to coordinate the blocks. This explains
two current traits:

- compilation is quick, but the result is not standalone;
- the first run may be slower while native artifacts are prepared, then cached runs
  avoid rebuilding them.

Generated files live in `.conflate/build` and are safe to delete.

## Shared values

| Python | C++ representation |
| --- | --- |
| `None` | null `conflate::Value` |
| `bool` | boolean `conflate::Value` |
| `int` | signed 64-bit `conflate::Value` |
| `float` | double `conflate::Value` |
| `str` | string `conflate::Value` |
| `list` or `tuple` | array `conflate::Value` |
| `dict[str, ...]` | object `conflate::Value` |

Other backends receive the same data through their natural dynamic container:

| Language | Incoming value |
| --- | --- |
| C++ | `conflate::Value` |
| Rust | generated `Value` enum |
| Java | `Object` containing `Long`, `Double`, `String`, `List`, or `Map` |
| Go | `any`; JSON numbers arrive as `float64` |

Functions, modules, classes, file handles, and custom Python objects stay inside
Python. They are not silently copied or stringified.

Imported values can be printed directly from C++:

```cpp
@python
words = ["one", "two", "three"]

@cpp
std::cout << words << "\n";
```

Convert a shared value when native C++ behavior is needed:

```cpp
auto text = value.as<std::string>();
auto items = value.as<conflate::Value::array_t>();
```

The other generated runtimes provide small conversion helpers:

```java
long count = conflateInt(sharedCount);
```

```go
count := conflateInt(sharedCount)
```

```rust
let count = shared_count.as_i64()?;
```

## Sending a native value back

Conflate recognizes straightforward declarations at the beginning of a line:

```cpp
@cpp
int answer = 6 * 7;

@python
print(answer)
```

An uninitialized declaration works too:

```cpp
@cpp
int n;
std::cin >> n;

@python
print(n)
```

Each backend recognizes common declarations at the start of a line: C++ scalar
and standard container declarations, Java primitive and collection declarations,
Go `var` and `:=`, and Rust `let`. A declaration hidden inside a macro, pattern,
or complicated statement may not be found.

Working examples are included in `examples/java.confl`, `examples/go.confl`, and
`examples/rust.confl`. `examples/all-languages.confl` passes one value through
all five backends and checks the result when every toolchain is installed.

## Cross-language functions

Define an ordinary top-level function, then call it from another block:

```cpp
@python
def square(n):
    return n * n

@cpp
std::cout << square(12);
```

This prints `144`. Functions become available when their defining block is
reached, and remain available until the program exits. Function names must be
unique across the file. Native workers are started on demand and reused; a
C++ function's static variable keeps its value between calls. Python functions
keep their normal globals and closures. These are in-memory lifetimes, not
saved state between separate program runs.

Native functions use ordinary declarations, with the header at the start of a
line. Java methods are made static automatically. Arguments cross as JSON
values; common scalar parameter types are converted at the worker boundary.
Use the existing value conversion helpers on a returned value when the calling
language needs a concrete type:

| Caller | Example |
| --- | --- |
| Python | `answer = square(12)` |
| C++ | `int answer = square(12).as<int>();` |
| Java | `long answer = conflateInt(square(12));` |
| Go | `answer := conflateInt(square(12))` |
| Rust | `let answer = square(12).as_i64()?;` |
| JavaScript | `let answer = square(12);` |

See `examples/functions.confl` and `examples/java-functions.confl` for retained
state and callbacks. The test suite also runs a nested call through C++, Java,
Go, Rust, and Python.

The `examples` directory also has focused demonstrations:

| File | What it demonstrates |
| --- | --- |
| `nested-functions.confl` | One nested call crossing every built-in language |
| `data-pipeline.confl` | Lists and numeric results moving through four native backends |
| `persistent-service.confl` | A C++ static counter called by Java and Python |
| `recoverable-errors.confl` | A Rust panic crossing Java and being caught in Python |
| `registered-javascript.confl` | Node.js registration and persistent JavaScript state |

Calls are synchronous, have a 60-second timeout, and use a private temporary
directory for messages. Standard input/output remain available to user code.
Exceptions are returned to the caller; worker crashes report the exit code.
Workers are shut down when execution ends, including on failure.

Current boundaries:

- Native functions cannot capture a preceding block's local variables. Pass
  those values as arguments. Their own static state stays in their worker.
- A callback into an already busy native worker is rejected. Ordinary recursion
  within a native worker works; cross-language recursive cycles do not yet.
- Generic signatures, overloads, receivers, async functions, pointers and
  arbitrary objects are outside the exported function format. Rust exports
  accept scalars, `String`, `&str`, or the generated `Value` type.
- Function arguments and results are copied. Mutating a received list does not
  mutate the caller's list; return the updated value explicitly.
- Python globals changed by callbacks are retained when the enclosing native
  block finishes. For a shared variable written by both, the callback's value
  wins. Avoid writing the same shared variable on both sides in one block.

## Adding languages

Point Conflate at an installed toolchain:

```powershell
conflate --add-language javascript node
conflate --add-language mycpp "C:\Tools\LLVM\bin\clang++.exe"
conflate --add-language customrust "C:\Tools\rustc.exe"
conflate --list-languages
conflate --remove-language mycpp
```

Conflate recognizes Python, g++/clang++, rustc, javac, go, and Node.js by their
executable names. Java registration also locates `java` next to `javac`. For a
renamed compatible compiler, use `--backend cpp` (or `python`, `java`, `go`,
`rust`, `javascript`). Registrations are saved in `~/.conflate/languages.json`.
Set `CONFLATE_CONFIG` to use a different file, such as a project configuration.
Removing a registration restores a built-in marker's default behavior.

After registering Node.js, this works:

```javascript
@javascript
function greet(name) { return "Hello, " + name; }
let count = 42;
@python
assert count == 42
print(greet("Conflate"))
```

An unfamiliar tool can be added with a JSON manifest, without changing
Conflate's Python code. For example, a Ruby interpreter that runs whole blocks:

```json
{
  "name": "ruby",
  "extension": ".rb",
  "run": ["ruby", "{source}"]
}
```

Register it with `conflate --language-manifest ruby.json`. A compiled language
can also supply `"compile": ["compiler", "{source}", "-o", "{output}"]` and
`"run": ["{output}"]`. Commands are argument arrays, executed without a shell.
Paths containing spaces stay single arguments. A `template` string may wrap
`{source}` in the language's required entry point.

The placeholders are `{source}` (generated file), `{output}` (binary), and
`{state}` (shared JSON object). A manifest can pass `{state}` to an existing
bridge executable, which reads it before the block and writes it afterward.
Without that bridge, raw blocks run but do not automatically share variables
or functions. The six recognized backends already supply their bridges.
An arbitrary compiler path cannot supply missing syntax and calling conventions.

## Troubleshooting

If `-r` says it expects a compiled `.exe`, compile the source first:

```powershell
conflate -c helloWorld.confl
conflate -r helloWorld.exe
```

If a toolchain is missing, install the command named in the error: `g++` or
`clang++` for the launcher and C++, `rustc` for Rust, `javac` plus `java` for
Java, and `go` for Go. `CXX` can point Conflate at a specific C++ compiler.

If a value is missing after crossing a block, check that it is JSON-compatible.
For a native value moving out of a block, keep its declaration simple and at the
beginning of a line.

## Development

Install the project in editable mode and run the standard-library test suite:

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
```

The implementation lives in `src/conflate`. There are no runtime Python
dependencies outside the standard library.

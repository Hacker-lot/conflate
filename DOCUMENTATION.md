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

This does not work yet:

```cpp
@python
def square(n):
    return n * n

@cpp
std::cout << square(12);
```

Supporting it properly requires persistent language workers and generated call
proxies. Faking it with text substitution would break as soon as a function had
state, side effects, or a non-trivial return type.

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

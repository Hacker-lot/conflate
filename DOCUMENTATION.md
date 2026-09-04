# Conflate documentation

Conflate treats one source file as a sequence of language blocks. The marker at
the start of a block chooses the language; the code below it stays ordinary code
for that language.

Version 0.1 supports Python and C++.

## File format

A Conflate source file uses the `.confl` extension:

```cpp
@python
name = input("Your name: ")

@cpp
std::cout << "Hello, " << name << "!\n";
```

Accepted markers are `@python`, `@py`, `@cpp`, and `@c++`. Code before the first
marker is an error. Blocks run in file order.

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
Python blocks run in one persistent Python environment. C++ blocks are wrapped in
a generated entry point and compiled with the C++ compiler available on the
machine.

Between blocks, Conflate serializes supported values as JSON. C++ receives those
values as `conflate::Value`; variables created by simple C++ declarations are
written back for the next block.

The generated launcher embeds a snapshot of the `.confl` source. When launched,
it uses the installed Conflate runtime to coordinate the blocks. This explains
two current traits:

- compilation is quick, but the result is not standalone;
- the first run may be slower while C++ artifacts are prepared, then cached runs
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

## Sending a C++ value back to Python

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

This recognizer covers common scalar types, `std::string`, `std::vector`,
`conflate::Value`, and `auto` when the resulting value can be serialized. A
declaration hidden inside a macro or complicated statement may not be found.

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

If no C++ compiler is found, install `g++` or `clang++` and put it on `PATH`.
You can also set the `CXX` environment variable to the compiler executable.

If a Python value is missing in C++, check that it is JSON-compatible. If a C++
value is missing in Python, keep its declaration simple and at the beginning of
a line.

## Development

Install the project in editable mode and run the standard-library test suite:

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
```

The implementation lives in `src/conflate`. There are no runtime Python
dependencies outside the standard library.

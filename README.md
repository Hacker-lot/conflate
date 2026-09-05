<p align="center">
  <img src="assets/conflate-icon.png" width="180" alt="Conflate logo">
</p>

<h1 align="center">Conflate</h1>

<p align="center">Mix Python, C++, Rust, Java, and Go in one file.</p>

Conflate is an experimental polyglot language runner. A `.confl` file contains
ordinary language blocks, and variables move between them without handwritten
bindings.

It is still early, but the language pipeline is real: each native block is
compiled by its own toolchain and shares state with the blocks around it.

## A quick example

```cpp
@python

def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

@cpp

int n;
std::cin >> n;

@python

print(fib(n))
```

Save that as `fib.confl`, then compile and run it:

```powershell
conflate -c fib.confl
conflate -r fib.exe
```

Enter `10`; Conflate prints `55`.

## Install from source

You need Python 3.11 or newer and a C++20 compiler named `g++` or `clang++`.
Programs using other blocks also need their normal tools: `rustc`, `javac` plus
`java`, or `go`. Put the commands on your `PATH`.

```powershell
git clone https://github.com/Hacker-lot/conflate.git
cd conflate
python -m pip install -e .
```

Then try the included example:

```powershell
cd examples
conflate -c helloWorld.confl
conflate -r helloWorld.exe
```

## What works today

- Python, C++, Rust, Java, and Go blocks execute from top to bottom.
- Strings, numbers, booleans, lists, dictionaries, and `None` cross the boundary.
- Simple native variables can return to later language blocks.
- Functions stay callable across blocks. Native workers keep function state
  until the program exits, and can call back into Python.
- Register another compiler or enable JavaScript by pointing Conflate at Node.js.
- Conflate generates entry points, state plumbing, and build commands.
- Compiled blocks are cached and reused when only input values change.

## What does not

- The generated executable is a launcher, not a standalone binary. It still needs
  Python, Conflate, and a C++ compiler on the machine where it runs.
- Native variable discovery is based on straightforward declarations, not full
  language parsers.
- Automatic integration needs known language conventions. Other tools can run
  through a command manifest; full value and function sharing needs a bridge.

Conflate is version `0.3.0`, and the format may change.

## Call a function across languages

```cpp
@python
def square(n):
    return n * n

@cpp
std::cout << square(12); // 144
```

C++ functions, Java methods, Go functions, Rust functions, and registered
JavaScript functions can return values to Python too. See
[`examples/functions.confl`](examples/functions.confl) for a counter that keeps
its state while the program switches languages. Calls use JSON messages, so a
call across languages costs more than a local function call.

## Add a language

```powershell
conflate --add-language javascript node
conflate --add-language mycpp "C:\Tools\LLVM\bin\clang++.exe"
conflate --list-languages
```

Now `@javascript` and `@mycpp` work in `.confl` files. No Conflate source edits
are needed. Python, g++/clang++, rustc, javac, go, and Node.js are recognized.
For an unfamiliar compiler, a [command manifest](DOCUMENTATION.md#adding-languages)
defines how to build and run its source. A compiler executable alone cannot
describe an arbitrary language's values or function signatures.

## More detail

Read [DOCUMENTATION.md](DOCUMENTATION.md) for the execution model, supported
types, CLI reference, examples, and current limits.

## Examples worth trying

- [`nested-functions.confl`](examples/nested-functions.confl) sends one function
  call through all five built-in languages and back.
- [`data-pipeline.confl`](examples/data-pipeline.confl) passes a list through Go,
  C++, Rust, and Java helpers before Python checks the result.
- [`persistent-service.confl`](examples/persistent-service.confl) proves that a
  C++ static counter survives calls from Java and Python.
- [`recoverable-errors.confl`](examples/recoverable-errors.confl) catches a Rust
  failure in Python, then calls the same Java and Rust workers again.
- [`registered-javascript.confl`](examples/registered-javascript.confl) adds
  Node.js without editing Conflate, then keeps JavaScript function state.

Bug reports and small, focused pull requests are welcome. Start with
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

Conflate is released under the [MIT License](LICENSE).

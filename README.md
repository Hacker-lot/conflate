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
- Conflate generates entry points, state plumbing, and build commands.
- Compiled blocks are cached and reused when only input values change.

## What does not

- Functions cannot yet be called directly across languages.
- The generated executable is a launcher, not a standalone binary. It still needs
  Python, Conflate, and a C++ compiler on the machine where it runs.
- Native variable discovery is based on straightforward declarations, not full
  language parsers.
- C#, JavaScript, and other languages are not implemented yet.

Those gaps are real. Conflate is version `0.2.0`, and the format may change.

## More detail

Read [DOCUMENTATION.md](DOCUMENTATION.md) for the execution model, supported
types, CLI reference, examples, and current limits.

Bug reports and small, focused pull requests are welcome. Start with
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

Conflate is released under the [MIT License](LICENSE).

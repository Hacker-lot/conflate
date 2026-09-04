<p align="center">
  <img src="assets/conflate-icon.png" width="180" alt="Conflate logo">
</p>

<h1 align="center">Conflate</h1>

<p align="center">Write Python. Drop into C++. Keep going.</p>

Conflate is an experimental polyglot language runner. A `.confl` file contains
ordinary language blocks, and variables move between them without handwritten
bindings.

It is small, early, and currently supports Python and C++. That is enough to
test the idea before pretending we have solved every language boundary.

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

You need Python 3.11 or newer and a C++20 compiler named `g++` or `clang++` on
your `PATH`.

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

- Python and C++ blocks execute from top to bottom.
- Strings, numbers, booleans, lists, dictionaries, and `None` cross the boundary.
- Simple C++ variables can return to later Python blocks.
- Conflate generates C++ entry points, headers, state plumbing, and build commands.
- Compiled C++ blocks are cached and reused when only the input values change.

## What does not

- Functions cannot yet be called directly across languages.
- The generated executable is a launcher, not a standalone binary. It still needs
  Python, Conflate, and a C++ compiler on the machine where it runs.
- C++ variable discovery is deliberately simple. It is not a full C++ parser.
- Rust, Go, Java, C#, and other languages are ideas, not implemented features.

Those gaps are real. Conflate is version `0.1.0`, and the format may change.

## More detail

Read [DOCUMENTATION.md](DOCUMENTATION.md) for the execution model, supported
types, CLI reference, examples, and current limits.

Bug reports and small, focused pull requests are welcome. Start with
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

Conflate is released under the [MIT License](LICENSE).

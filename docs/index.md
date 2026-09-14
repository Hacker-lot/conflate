---
layout: default
---

# Use the language that fits each part of the job

Conflate is an experimental polyglot language for using Python, C++, Rust, Java, and Go in one
`.confl` file. Each block keeps the language's normal syntax and libraries. You
declare the values a block reads and publishes; Conflate prepares the entry
points and JSON bridges between them.

The point is practical: use Python where quick data handling and its ecosystem
save time, Rust where memory-safe parsing and checked arithmetic matter, C++ for
native code you already have, and Java for an existing library or service. Go,
PHP, and JavaScript can fit the same setup through their supported integrations.
Conflate handles the data exchange, so you can change the Python workflow
without rewriting the Rust code or building a separate wrapper.

[View the source](https://github.com/Hacker-lot/conflate) ·
[Install the release](https://github.com/Hacker-lot/conflate/releases/tag/v0.4.0) ·
[Read the language specification](https://github.com/Hacker-lot/conflate/blob/main/docs/LANGUAGE.md)

![Python, C++, Rust, Java and Go exchanging a typed value](https://raw.githubusercontent.com/Hacker-lot/conflate/main/assets/polyglot-tour.gif)

The animation comes from the five-language example below. It is a compact way
to see the syntax; the smaller Python and Rust example shows a more typical use
of the runtime.

## Start with Python and Rust

The [orders example](https://github.com/Hacker-lot/conflate/blob/main/examples/rust-python-orders.confl)
has Python provide order rows as strings and format the final report. Rust
parses the quantities and cents, uses checked arithmetic, and rejects malformed,
negative, or overflowing rows. Change the report in Python; keep the validation rules together in Rust.

```sh
conflate --run-source examples/rust-python-orders.confl
```

The [example notes](https://github.com/Hacker-lot/conflate/blob/main/docs/RUST-PYTHON.md)
include the sample output and explain the validation choices.

## Try the full tour

Install Python 3.11+ and the toolchains for the blocks you want to run. The full
tour uses `g++` or `clang++`, `rustc`, `javac` plus `java`, and `go`.

```sh
git clone https://github.com/Hacker-lot/conflate.git
cd conflate
python -m pip install -e .
conflate --doctor
conflate --run-source examples/polyglot-tour.confl
```

The checked output is:

```text
Python -> C++ -> Rust -> Java -> Go -> Python: 40, 42, 43, 44, 45
```

[Inspect every block](https://github.com/Hacker-lot/conflate/blob/main/docs/POLYGLOT-TOUR.md). If you only have a subset of the
toolchains installed, start with the matching [smaller examples](https://github.com/Hacker-lot/conflate/tree/main/examples).

## Make boundaries explicit

Each block can declare which values it reads and publishes:

```text
@rust(in: cpp_value: int; out: rust_value: int)
let rust_value: i64 = cpp_value.as_i64()? + 1;

@java(in: rust_value: int; out: java_value: int)
long java_value = conflateInt(rust_value) + 1;
```

Conflate checks those values at runtime. Unpublished locals stay local, and
previous shared values remain available for later blocks that import them.
Bare markers retain implicit sharing for existing programs.

## PHP, JavaScript, and more

Python, C++, Rust, Java, and Go are built in. Node.js is a recognized registered
backend with value sharing and persistent function workers. PHP is available
through an optional [JSON command-manifest bridge](https://github.com/Hacker-lot/conflate/blob/main/docs/PHP.md), which shares
values but does not export cross-language function workers.

Other runtimes can use the command-manifest interface. Each language needs a
bridge to participate in value sharing; an arbitrary compiler path does not
make all languages interchangeable.

## An experiment you can inspect

This is a process-based orchestration language. It is not a standalone binary
compiler, zero-copy FFI, or a whole-program static type checker. Installed
toolchains are still required. JSON copying has overhead, and the documented
native signature and numeric precision limits matter.

The useful question is where explicit polyglot blocks make an experiment easier
to read and change. Try a small program, inspect the generated native artifacts,
and [report a reproducible problem or discuss an extension](https://github.com/Hacker-lot/conflate/issues).

Conflate is free software under the MIT license. If the project is useful to
you, a [GitHub star](https://github.com/Hacker-lot/conflate) helps others find it.

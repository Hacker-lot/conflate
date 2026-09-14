# Conflate language specification

Conflate is a small polyglot orchestration language. A `.confl` file is a
sequence of ordinary Python, C++, Rust, Java, or Go blocks. Conflate runs each
block with that language's normal toolchain and moves portable values across
the boundaries. It coordinates programs; it does not try to replace the
languages with one shared grammar.

The block contract syntax makes those boundaries readable and checkable. It is
useful when a file is large enough that an implicit shared namespace becomes
hard to review, and it gives native blocks a known input set when they are
compiled.

## Source structure

Every block starts with a marker on its own line. Code before the first marker
is rejected, and blocks run from top to bottom.

```text
@language
ordinary source for language
```

`language` is one of `python`, `cpp`, `rust`, `java`, or `go` (with the aliases
documented in `DOCUMENTATION.md`). A marker may include an optional contract:

```text
@language(in: name: type, name: type; out: name: type, name: type)
ordinary source for language
```

The grammar is:

```text
marker  = "@" language [contract]
contract = "(" [clause {";" clause }] ")"
clause  = ("in" | "out") ":" binding {"," binding}
binding = identifier ":" type
type    = "int" | "float" | "bool" | "str" | "list" | "dict" | "any"
```

There can be at most one `in` clause and one `out` clause. Names must be valid
identifiers and cannot be repeated within a clause, although the same name may
appear once in each direction. Whitespace is allowed around names, colons,
commas, and semicolons. Type names are case-insensitive. The inner clauses are
optional, so `@python()` is a valid explicit empty contract. An omitted `in`
clause imports nothing, and an omitted `out` clause exports nothing; for
example, `@python(out: answer: int)` has no inputs.

## Contract semantics

An explicit contract describes values at one block boundary:

- `in` is the complete set of shared values imported by the block. A missing
  name or a value with the wrong type is an error before the block runs.
- `out` is the complete set of values the block exports. Every listed output
  must be produced and must have the declared type, or the block fails after it
  runs.
- Values from earlier blocks remain in shared state while the block runs. After
  the block finishes, the listed outputs replace values with the same names;
  other existing shared values are preserved for later blocks.
- A contract with no `out` clause exports no new values. It can still print,
  perform I/O, and call registered functions.
- Imported lists and dictionaries are recursively copied at the boundary.
  Mutating nested data inside a block does not mutate the preserved prior state
  unless that name is also listed in `out`.
- A name may be both an input and an output when a block updates a value in
  place. For example:

  ```confl
  @python(out: x: int)
  x = 40

  @python(in: x: int; out: x: int)
  x += 2
  ```

The contract controls values crossing the block boundary. It does not change
the source language inside the block: Python remains Python, C++ remains C++,
and so on. The runtime checks portable values at the boundary and reports the
source location of a missing name or type mismatch.

`conflate --check file.confl` validates markers, contract syntax, and Python
syntax without executing blocks. It does not statically type-check native
source or prove that a contract's values will be present and correctly typed;
those input and output checks happen when the program runs.

Bare markers such as `@python` keep the legacy implicit behavior: the block
sees the current shared values and straightforward portable assignments are
available to later blocks. This keeps existing `.confl` files compatible while
allowing new files to opt into explicit contracts one block at a time.

## Portable types

The boundary format is JSON-shaped. The contract types mean:

| Type | Accepted value |
| --- | --- |
| `int` | Signed integer in the portable 64-bit range |
| `float` | Finite integer or floating-point value; integers are accepted and cross as numeric values |
| `bool` | Boolean (`True`/`False`), not an integer substitute |
| `str` | String |
| `list` | List whose nested values are portable |
| `dict` | Dictionary with string keys and portable values |
| `any` | Any portable value, including `null`/`None` |

Portable nested values are booleans, integers, finite floats, strings, lists,
dictionaries with string keys, and `None`/`null`. Functions, modules, classes,
file handles, and custom objects stay in their host runtime and cannot be
exported as shared values. A tuple is serialized as a list in an implicit
boundary, but an explicit `list` contract expects a list value in the source
runtime.

Native blocks receive generated runtime values. For example, an imported C++
value is a `conflate::Value` and can be converted with `value.as<int>()`,
`value.as<double>()`, or the other helpers described in
`DOCUMENTATION.md`. The contract describes the value at the boundary; it does
not turn that value into a native declaration automatically.

The contract validator accepts signed 64-bit `int` values. JSON numbers in the
Go runtime, and in registered JavaScript runtimes, are decoded as IEEE-754
`float64` values, so integers above `2**53 - 1` can lose precision when they
cross those backends. Keep exact cross-language integers within that safe range
when a pipeline includes Go or JavaScript, or use `str` for larger identifiers.

## Functions and state

Top-level function and native worker declarations use Conflate's separate
callable registry. They remain callable after their defining block is reached,
and native workers may retain their own in-process state until the program
exits. Block contracts govern shared data values; they do not export function
definitions or make function signatures part of the `in`/`out` list.

The generated executable is a launcher for the Conflate runtime, not a
standalone binary. Running it still needs Python, Conflate, and the toolchains
required by its blocks. Native artifacts and JSON state are cached under
`.conflate/build`.

## Complete example

This is the smallest useful typed pipeline: Python produces two values, C++
imports only the integer and computes a result, and the final Python block
imports the result and the preserved label.

```confl
@python(out: seed: int, label: str)
seed = 14
label = "typed pipeline"

@cpp(in: seed: int; out: answer: int)
int answer = seed.as<int>() * 3;
std::cout << "C++ computed " << answer << "\n";

@python(in: answer: int, label: str)
print(f"{label}: {answer}")
```

Run it with:

```powershell
conflate --run-source examples/typed-pipeline.confl
```

The output is:

```text
C++ computed 42
typed pipeline: 42
```

The C++ block cannot read `label`, because it is not in its `in` clause. The
label is still preserved in shared state and can be imported by the final
Python block.

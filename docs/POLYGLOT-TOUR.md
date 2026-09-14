# Polyglot tour

`examples/polyglot-tour.confl` is a small typed handoff through every native
backend currently included with Conflate:

```text
Python → C++ → Rust → Java → Go → Python
```

Python starts with `seed = 40`. Each native block imports one integer through
an explicit `in` contract, adds one step, and exports a new integer through an
explicit `out` contract. The final Python block checks every value and prints:

```text
Python -> C++ -> Rust -> Java -> Go -> Python: 40, 42, 43, 44, 45
```

Run the source from the repository root after installing the documented
toolchains:

```powershell
conflate --check examples/polyglot-tour.confl
conflate --run-source examples/polyglot-tour.confl
```

To execute the tour and regenerate the walkthrough GIF, install Pillow in your
development environment and run:

```powershell
python -m pip install Pillow
python scripts/render_launch_demo.py
```

The script adds `~/.cargo/bin` to the child process's `PATH` if present, executes
the tour, verifies the exact output, reads the six source blocks, and writes
`assets/polyglot-tour.gif`. It fails before writing the GIF if execution or
verification fails.

The generated launcher still needs the Conflate runtime and the toolchains
used by its blocks. See [the language specification](LANGUAGE.md) for the
contract grammar and boundary semantics.

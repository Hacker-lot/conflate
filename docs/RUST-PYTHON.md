# Rust for validation, Python for the rest

Suppose you have a Python script that pulls orders from an API and builds a
report. You want strict rules around quantities and prices, but you still want
to change the report with a few lines of Python.

[This example](../examples/rust-python-orders.confl) puts those jobs in the same
file. Python supplies the rows. Rust parses them and calculates each order's
total in integer cents. Python takes the accepted totals and formats the report.
Conflate passes the declared values between the blocks.

```sh
conflate --run-source examples/rust-python-orders.confl
```

Install Conflate and put `rustc` on your PATH first. The output is:

```text
Accepted 2 orders; rejected 3
Revenue: USD 39.48
```

The rejected rows contain a malformed number, a negative quantity, and an
integer multiplication that would overflow. Rust handles each as an ordinary
rejection, using `parse` and `checked_mul`. Its safe code also gets Rust's
memory-safety checks. Those checks apply to the Rust code; input rules still
need to be written, as they are here.

Try changing the currency label or adding a summary in the last Python block.
The Rust code stays the same, and Conflate reuses the cached compiled block.
In a larger script, Python could handle API clients, pandas, or a plotting
library while Rust handles a batch of data with explicit validation rules.

This saves the work of writing a separate command-line wrapper and arranging
the data exchange yourself. Values are copied between processes as JSON, so
send a batch across each boundary rather than calling across it for every row.
The example demonstrates how to divide the work; it does not measure throughput.

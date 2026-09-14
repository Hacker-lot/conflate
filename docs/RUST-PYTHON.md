# Rust for validation, Python for the rest

Suppose you have a Python script that pulls orders from an API and builds a
report. You want strict rules around quantities and prices, but you still want
to change the report with a few lines of Python.

[This example](../examples/rust-python-orders.confl) puts those jobs in the same
file. Python supplies the rows. Rust parses them and calculates each order's
total in integer cents. Python takes the accepted totals and formats the report.
Conflate passes the declared values between the blocks.

Here is the Rust block. `orders` contains one `quantity,price` pair per line;
`price` is an integer number of cents.

```rust
@rust(in: orders: str; out: totals: list, rejected: int)
let mut totals: Vec<i64> = Vec::new();
let mut rejected: i64 = 0;
for row in orders.as_str()?.lines() {
    let total = row.split_once(',').and_then(|(quantity, price)| {
        let quantity = quantity.trim().parse::<i64>().ok()?;
        let price = price.trim().parse::<i64>().ok()?;
        if quantity <= 0 || price < 0 { return None; }
        quantity.checked_mul(price)
    });
    match total {
        Some(cents) => totals.push(cents),
        None => rejected += 1,
    }
}
```

The first line is Conflate syntax; the body is Rust. `split_once` returns
`None` when a row has no comma. Inside `and_then`, each `.ok()?` turns a failed
integer parse into an early `None` for that row. Valid integers still need
business rules: quantities must be positive and prices cannot be negative.
Finally, `checked_mul` returns `None` if the total cannot fit in an `i64`.
The `match` keeps rejected rows out of `totals` without stopping the batch.

This deliberately uses a two-field format. For a real CSV feed with quoted
fields or embedded commas, use a CSV parser and keep the same validation steps.

The report is ordinary Python:

```python
@python(in: totals: list, rejected: int)
from decimal import Decimal
currency = "USD"
revenue = Decimal(sum(totals)) / 100
print(f"Accepted {len(totals)} orders; rejected {rejected}")
print(f"Revenue: {currency} {revenue:.2f}")
```

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

Authorship: this tutorial and example were written with AI assistance as part
of Conflate's development. The example is run in the project's integration tests.

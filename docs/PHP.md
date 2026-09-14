# PHP command-manifest integration

Conflate can run PHP 8 or newer blocks through the external command-manifest interface.
This keeps PHP optional: it is a user supplied command, not a built-in
Conflate backend.

The example manifest is [examples/php-language.json](../examples/php-language.json).
Register it in an isolated configuration file when trying the example:

```powershell
$env:CONFLATE_CONFIG = "$PWD/.conflate/php-languages.json"
conflate --language-manifest examples/php-language.json
conflate --run-source examples/php-roundtrip.confl
```

The manifest runs `php {source} {state}`. The template reads the JSON object at
the state path from `argv`, creates PHP variables for its simple named values,
and inserts the block source at `{source}`. After the block finishes it writes
the user variables back as a JSON object. Wrapper variables use the reserved
`__conflate_` prefix and are excluded from the exported object; PHP's command
line and server superglobals are excluded as well. State keys using either
reserved names or the `__conflate_` prefix are rejected before assignment.

The bridge carries JSON-shaped portable values: null, booleans, finite numbers,
strings, and recursively portable PHP arrays. JSON objects imported from the
state file become associative PHP arrays; empty arrays and empty objects remain
distinct only at the JSON boundary. Exported PHP objects, resources, closures,
and other values outside that set cause the command to exit nonzero. `in` and `out` contracts still belong
to Conflate: the template exports the user state it can serialize, and the
runtime applies the declared `out` filter and type checks at the block
boundary.

This integration passes values through a state file. It does not register PHP
functions in Conflate and it does not provide native PHP-to-Python or
PHP-to-C++ calls. For a complete small pipeline, see
[examples/php-roundtrip.confl](../examples/php-roundtrip.confl): Python writes
two values, PHP computes and prints a result, and Python reads the declared
outputs back.

The test is skipped when `php` is not on `PATH`. With PHP installed it checks
manifest registration, the round trip, and a failing PHP block's nonzero exit.

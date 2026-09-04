# Contributing

Conflate is still proving its basic model. Small fixes and focused experiments
are more useful than large frameworks built for hypothetical features.

## Before opening a pull request

1. Open an issue for syntax changes or new language backends.
2. Keep existing `.confl` programs working unless the change is intentionally
   breaking and documented.
3. Add one regression test for a bug fix or new behavior.
4. Run `python -m unittest discover -s tests -v`.

Please keep error messages direct and documentation honest about what works.

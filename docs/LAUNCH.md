# Launch plan

The launch goal is a small, honest release that people can reproduce quickly:
clone Conflate, install the documented toolchains, run the typed pipeline, and
inspect the contract implementation. The working claim is “a polyglot
orchestration language with explicit typed block boundaries,” backed by the
source, tests, and the output of `examples/polyglot-tour.confl`. The launch
demonstrates Python, C++, Rust, Java, and Go together, plus the optional PHP
command-manifest bridge; it is not limited to Python and C++.

The project starts from 1 GitHub star, checked on 2026-09-14 at 12:10 UTC. The
three-day observation window ends on 2026-09-17 at 12:10 UTC. Reaching at least 101
stars is an aspiration and a useful signal, not a promise. We will record the
starting count, the release time, links to each public announcement, and the
ending count so the result is reproducible.

## Before release

1. Run the normal test suite and the typed example on a clean checkout with
   Python 3.11+ and the documented C++ compiler. Confirm that the example
   prints `C++ computed 42` and `typed pipeline: 42`.
2. Check the source line numbers and links in `README.md`,
   `DOCUMENTATION.md`, and `docs/LANGUAGE.md`. Keep the scope claim limited to
   the supported backends and the current runtime requirements.
3. Create a GitHub release with a short changelog, the example command, and a
   link to the language specification. Include the known limitation that the
   compiled result is a launcher and still needs the Conflate runtime and
   toolchains.
4. Prepare a short screen recording or terminal capture of the reproducible
   example. Show the source, command, and output; do not imply benchmarks or
   adoption that have not been measured.

## Three-day schedule

| Time | Action | Evidence to keep |
| --- | --- | --- |
| Day 0 | Tag the release and publish the GitHub release | Tag, release URL, test command and output |
| Day 0 | Share the release from an account that can answer technical questions | Public post URL and timestamp |
| Day 1 | Reply to genuine questions and fix only verified defects | Issue or discussion links, commit links |
| Day 2 | Publish one follow-up demo or implementation note if there is a real question to answer | Demo URL and topic |
| Day 3 | Record the GitHub star count at the deadline | UTC timestamp, count, and observation notes |

Keep the launch quiet while the state is unchanged. Respond to substantive
questions, correct factual errors, and update the release notes when behavior
changes. Do not use bots, bought stars, incentives, vote rings, bulk messages,
or spam. Do not ask people to star in exchange for access or support.

## Publication checklist

Write each public post in your own voice and link to the same reproducible
artifact. A useful post answers four questions in a few sentences: what
Conflate is, what the typed contracts add, how to run the example, and what the
current limitations are. Include the repository and release links, then invite
technical feedback rather than asking for votes.

Use the following as factual prompts while writing:

- “Conflate runs ordinary Python, C++, Rust, Java, and Go blocks from one
  `.confl` file.”
- “Version 0.4 adds optional `in`/`out` clauses with the types `int`, `float`,
  `bool`, `str`, `list`, `dict`, and `any`.”
- “The example sends `seed` from Python to C++, computes `42`, and prints the
  result in Python. Run `conflate --run-source
  examples/typed-pipeline.confl` after installing the documented toolchains.”
- “The generated executable is a launcher and requires the Conflate runtime and
  language toolchains.”

Before using a community forum, read its current rules and follow its required
format. Hacker News asks users not to submit generated or AI-edited text; write
any submission there independently and disclose the project accurately. The
Programming Languages subreddit currently has rules that can exclude projects
whose code or documentation depends on LLM generation, so do not use it as a
launch channel unless the current moderators' rules clearly permit this
project. See the [Hacker News guidelines](https://news.ycombinator.com/newsguidelines.html)
and [r/ProgrammingLanguages rules](https://www.reddit.com/r/ProgrammingLanguages/about/rules/)
before posting.

## Measurement

At the deadline, record the GitHub star count, forks, release views if GitHub
exposes them, and the number of substantive issues or discussions. Separate
organic interest from direct announcements in the notes. Report the actual
numbers, including a result below 101; the value of the launch is the public,
repeatable demonstration and the quality of the feedback, not a guaranteed
metric.

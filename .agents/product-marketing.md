# Product Marketing Context

**Document version:** v1
**Last updated:** 2026-09-14

## Product Overview

**One-liner:** One program, several languages, explicit boundaries.
**What it does:** Conflate composes ordinary language blocks in a `.confl`
file. It generates native entry points and JSON bridges, validates typed block
inputs and outputs, and supports persistent cross-language function workers.
**Category:** Experimental polyglot orchestration language and developer tool.
**Business model:** Free, MIT-licensed open source. No subscriptions or paid funnel.

## Audience and Use Cases

Developers who already work across languages: Python, C++, Rust, Java, Go,
JavaScript, PHP, and other runtimes. The broad language vision is central;
never position Conflate as only a Python/C++ binding tool.

Primary hypotheses, not validated customer segments: developers prototyping
mixed-language utilities; language-tool enthusiasts exploring interoperability;
educators illustrating value boundaries; contributors building more backends.

Useful examples include a value passing through five language toolchains,
data prepared in one language and transformed in another, and adding an
interpreter through a command manifest. Do not imply that people should split
a trivial production calculation across five processes for performance.

## Scope and Claims

| Capability | Current evidence |
| --- | --- |
| Python, C++, Rust, Java, Go | Built-in execution and value bridges, exercised by native tests |
| JavaScript | Recognized Node.js registration with value/function bridge |
| PHP and other languages | Extensible command-manifest route; each bridge/example must be verified individually |
| Typed inputs/outputs | Runtime boundary checks; ordinary host-language bodies |
| Local builds | Source snapshot, manifest, prepared native cache; Python/runtime/toolchains remain required |

Never claim native PHP function-worker parity unless it has been implemented
and tested. Never claim standalone binaries, zero-copy interoperability,
whole-program static typing, speedups, adoption, or customer endorsements
without evidence. Go/JavaScript number precision and process/JSON overhead
are documented limitations.

## Positioning and Alternatives

The appeal is seeing and running multiple language blocks together with
explicit data contracts. Alternatives include separate scripts, command-line
pipelines, language-specific bindings, and existing interoperability runtimes.
We have not established categorical superiority over those alternatives.
The launch should show the code and invite technical evaluation.

## Objections

| Question | Response |
| --- | --- |
| Why not just use one language? | Often that is the better choice; Conflate is for experiments that already cross runtimes. |
| Is this one native binary? | No. It coordinates installed runtimes and compiled native blocks. |
| Does every language have the same integration? | No. State the difference between built-ins, recognized registrations, and command manifests. |
| Is it production ready? | Experimental. Review the documented limits and test your workload. |

## Voice and Evidence

Direct, curious, technical, readable. Lead with working source and output.
No invented testimonials, benchmarks, urgency, user counts, or engagement.
No customer interviews or independent testimonials are available yet.

Verified release: https://github.com/Hacker-lot/conflate/releases/tag/v0.4.0
Verified CI: https://github.com/Hacker-lot/conflate/actions/runs/34848092076
Local clean-wheel installation and all five installed toolchains were tested.

## Goals and Distribution

User target: exceed 100 real GitHub stars during the three-day launch window
ending 2026-09-17 12:10 UTC. Initial count was 1. Report actual progress; the
target is not guaranteed. Also track successful trials, asset downloads, and
substantive issues, which distinguish interest from passive clicks.

User authorizes autonomous legitimate promotion without repeated consultation.
Use available authenticated publishing routes and relevant public submission
forms; do not create accounts under invented identities or evade platform rules.
No bought stars, fake accounts, mass DMs, vote swaps, or incentives for stars.
Hacker News prohibits generated/AI-edited posts; do not submit generated copy.
r/ProgrammingLanguages excludes LLM-generated projects; do not submit there.

## Changelog

- v1 (2026-09-14): Captured the user's broad polyglot positioning, verified
  capabilities, current integration limits, and autonomous launch constraints.

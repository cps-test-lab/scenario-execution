# AGENTS.md — working agreements for scenario-execution

Project **invariants** for any agent or contributor changing this repository: what a change
must hold, not how the system works. How it works is in `docs/`, linked from here and never
restated — a copy of a documented fact is a second source that will disagree.

## 1. A change to the DSL surface is done when an author can find it

An action or modifier reaches a scenario through three artifacts, and all three move together
or the feature is invisible, unusable, or undiscoverable.

- The `.osc` declaration in a `lib_osc/` library, the behavior, and its entry point in the
  owning package's `setup.py` — an action with no entry point parses, then fails at tree build.
- The reference table in `docs/libraries.rst`, and the keyword table in
  `docs/openscenarioDSL.rst`, "Supported features" — a stale ❌ there sends readers building
  workarounds for something that works.
- **Then ask whether it needs a pattern.** `docs/openscenarioDSL.rst`, "Patterns" holds use
  cases that took more than one attempt to express; the reference says a keyword exists, a
  pattern says what to write with it. Add one when a change makes a use case newly
  expressible, or when the feature only makes sense combined with others.

## 2. The tree owns an action's lifecycle

`docs/architecture.rst`, "Action Lifecycle" — a shared tick, what an invalidated branch must
stop, and why actions never reference each other. Each is a class of bug the composites exist
to prevent, not a style preference.

- Read it before adding an action that starts anything the tree cannot see.

## 3. Fail loudly — a silent no-op is worse than an error

A scenario's verdict is the product, and a green run nobody investigates is more expensive
than a red one.

- Prefer `FAILURE` naming what could not be done over `SUCCESS` that skipped it.
- Make "I cannot do this" an explicit answer rather than an absence.

## 4. Middleware stays out of the core

`scenario_execution` runs without ROS; `scenario_execution_ros` and `libs/*` add it.

- A concept that applies to a process or a container as much as to a goal belongs in the core,
  named for what it does rather than the mechanism that prompted it.
- Core tests must not need ROS — `scenario_execution/test/` exercises behavior through the
  parser and `run_process` alone, which is what keeps that independence honest.

## 5. Comments in a scenario `.osc` are short and rare

A scenario is configuration, not prose. Comment only what needs explaining — a value that
would otherwise read as arbitrary, or the constraint that fixes it.

- Prefer a short inline `#` comment on the line it explains; a standalone comment is **at most
  two lines**.
- No section banners, no restating the action name, no recording what a value used to be.
- A `lib_osc/` library is the exception: the trailing `#` on a parameter is its documentation,
  and it must agree with `docs/libraries.rst`.

## 6. An addition to this file follows these rules

Add a rule here only when it constrains a change and no test can. Everything else is docs, or
a test.

- Keep it to a lead of at most three lines plus one level of bullets, and add no third level.
- A current fact about how scenario-execution works goes in `docs/` and is referenced from
  here, never written out twice.
- State the rule, not the scenario or the run that revealed it.

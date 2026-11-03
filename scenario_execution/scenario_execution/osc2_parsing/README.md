# OSC2 parser generation

The lexer, parser, listener and visitor in this directory are **generated** from
`OpenSCENARIO2.g4` and committed. Regenerate them from the repository root with:

``` bash
make parser
```

That fetches the pinned ANTLR jar, runs the generator, and re-applies the edits ANTLR does
not emit (see `tools/antlr_postprocess.py`). Do not call `java -jar antlr...` by hand: the
generator overwrites its output wholesale, so a manual run silently drops the license
headers and reintroduces a `typing.io` import that does not exist on Python 3.13.

**The version is pinned to 4.9.1** — the version the committed files were generated with.
ANTLR 4.10+ changes the Python runtime API (notably the `serializedATN` representation), so
bumping it means moving the `antlr4-python3-runtime` pin in `requirements.txt` and
`setup.py` in lockstep, and is a change in its own right.

## Checking a regeneration

Regenerating the *unmodified* grammar reproduces the committed files byte for byte. That
makes it worth running `make parser` before touching the grammar: if `git diff` is not
empty at that point, the toolchain differs from the one that produced the tree, and any
later diff cannot be attributed to the grammar change.

A grammar change confined to the lexer should leave `OpenSCENARIO2Parser.py`,
`OpenSCENARIO2Listener.py`, `OpenSCENARIO2Visitor.py` and the `.tokens` files untouched.

## No semantic predicates in the lexer

The lexer deliberately has **no** `{...}?` predicates. A predicate reachable from a mode's
start closure makes ANTLR set `suppressEdge` in `LexerATNSimulator.matchATN`, so `dfa.s0`
is never memoized and every token of every file re-runs full ATN start-state simulation
instead of reusing the DFA. When `NEWLINE` still carried a start-of-input predicate this
cost roughly 1.2 s to parse a scenario with its imports, against 0.15 s without it.

If you add a predicate, expect to pay that back. `test_lexer_dfa_cache.py` guards it.

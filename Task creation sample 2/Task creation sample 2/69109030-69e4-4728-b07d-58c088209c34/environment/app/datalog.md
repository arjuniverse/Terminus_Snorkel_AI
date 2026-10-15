# stratdl — stratified Datalog evaluator: binding specification

This document is the authoritative contract the verifier checks against. Where it
and the task prompt differ, this document wins. The report is graded for an exact
byte-for-byte match.

## Runtime

The wrapper is invoked as `/app/stratdl <input_path> <output_path>`. It loads
`/app/src/stratdl.pl` and calls `run/2` with the two paths. The process must exit
with status `0` on success and `1` if the program is rejected (any error below).
GNU Prolog standard predicates and the bundled `lists`/`assoc` libraries are fair
game.

## Input: a Datalog program

The input file is a Datalog program. It is read line by line; **line numbers are
1-based over the raw file lines** (blank and comment lines included in the count).

For each raw line, in order: everything from the first `%` to the end of the line
is a comment and is removed, then surrounding whitespace is stripped. A line that
is empty after that is ignored (it is not a clause, but it still consumes a line
number). Every other line is exactly **one clause** and must end with `.`.

### Grammar

```
clause   := atom [ ':-' literal (',' literal)* ] '.'
literal  := [ 'not' ] atom
atom     := ident '(' term (',' term)* ')'
term     := ident | var
ident    := [a-z][A-Za-z0-9_]*          % predicate names and constants
var      := [A-Z][A-Za-z0-9_]*          % variables
```

Whitespace (spaces/tabs) may appear between tokens. Every atom has at least one
argument. A clause with no body (`atom.`) is a **fact**; a clause with a body
(`head :- l1, l2, ….`) is a **rule**. `not` is the negation keyword and applies to
a single atom. Constants and predicate names are lowercase-initial identifiers;
variables are uppercase-initial.

### Well-formedness (checked in this order; the first failure is reported)

1. **malformed clause** — a non-empty line that does not parse as a clause per the
   grammar above (missing trailing `.`, bad token, unbalanced parentheses, empty
   head, a literal that is not an atom, etc.). Reported at the line where it
   occurs.
2. **arity mismatch** — a predicate name is used with two different numbers of
   arguments anywhere in the program. Scanning clauses top to bottom and, within a
   clause, the head first then the body literals left to right, the first atom
   whose arity disagrees with that predicate's first-seen arity is the offender.
3. **non-ground fact** — a fact (a clause with no body) that contains a variable.
4. **unsafe rule** — a rule in which some variable appearing in the head, or in a
   negated body literal, does **not** also appear in at least one positive
   (non-negated) body literal. (This "safety" condition guarantees every derived
   fact and every negation test is ground.)
5. **program not stratifiable** — see below.

Checks 1–4 run in the listed order over the whole program; check 5 runs last.

## Stratification

Build the predicate dependency graph: for every rule with head predicate `H` and
every body literal whose predicate is `B`, add an edge `B → H`, marked *negative*
when that literal is negated. The program is **stratifiable** iff no cycle of the
graph contains a negative edge (equivalently, no predicate depends negatively,
directly or transitively, on itself). A program that is not stratifiable is
rejected with `program not stratifiable`.

For a stratifiable program a *stratification* assigns each predicate an integer
stratum so that for every positive edge `B → H`, `stratum(H) ≥ stratum(B)`, and
for every negative edge `B → H`, `stratum(H) > stratum(B)`.

## Semantics: the perfect model

The program denotes its **perfect model**: the unique set of ground facts `M`
such that

- every fact (body-less clause) is in `M`;
- `M` is closed under every rule — for each rule and each assignment of constants
  to its variables under which every positive body literal is in `M` and every
  negated body literal `not q(…)` has its ground atom **absent** from `M`, the
  correspondingly instantiated head is in `M`;
- `M` is minimal / supported: every fact in `M` is justified by the facts and by
  rule firings evaluated stratum by stratum (lower strata first, so a negated
  predicate is fully determined before it is tested — closed-world negation).

For a stratifiable program this `M` exists, is unique, and does not depend on
which valid stratification is chosen.

## Output: the canonical model

On success write, to the output file:

1. A first line `facts: <N>` where `<N>` is the total number of facts in the
   perfect model.
2. Then one line per fact, as `pred(arg1,arg2,…)` — the predicate name, then its
   arguments (all constants) joined by single commas, no spaces, inside one pair
   of parentheses.

The facts are listed in a single canonical order: ascending by predicate name,
then by arity (argument count), then by argument tuple compared left to right.
Names, constants, and the ordering all use ordinary ASCII/lexicographic
comparison. Every line (including the `facts:` line) ends with a newline, and the
file ends with exactly one trailing newline. A program whose model is empty
produces just `facts: 0`.

### Example

Program:

```
edge(a, b).
edge(b, c).
path(X, Y) :- edge(X, Y).
path(X, Y) :- edge(X, Z), path(Z, Y).
```

Output:

```
facts: 5
edge(a,b)
edge(b,c)
path(a,b)
path(a,c)
path(b,c)
```

## Errors

On any rejected program write a single line `Error: <reason>` (and nothing else)
and exit 1. The exact reasons and their order of precedence are:

```
Error: malformed clause at line <N>
Error: arity mismatch for <pred> at line <N>
Error: non-ground fact at line <N>
Error: unsafe rule at line <N>
Error: program not stratifiable
```

The first applicable error in that order is the one reported; `<N>` is the
1-based raw line number, and `<pred>` is the predicate name.

## Anti-cheat

The implementation must be in GNU Prolog. The wrapper invokes `gprolog` with
`--consult-file` on the source. The verifier statically rejects sources that
shell out or escape the Prolog runtime — it forbids the tokens `system/1`,
`system/2`, `exec/`, `popen/`, `socket_`, and `process_create`, and the
foreign-function / C-bridge call forms `foreign(...)`, `:- foreign`,
`foreign_file(...)`, and `c_code(...)`. Implement the evaluator in plain GNU
Prolog; do not open network sockets, call other interpreters, or drop into C.

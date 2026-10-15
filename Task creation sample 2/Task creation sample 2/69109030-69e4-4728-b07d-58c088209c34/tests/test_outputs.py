"""Verifier for the stratdl-gp task.

Each test writes a Datalog program to a temp file, invokes /app/stratdl, and
asserts on the resulting output text per the binding spec in /app/datalog.md.

Two layers of checks:
  * targeted cases with the exact expected report text (readable diagnostics and
    coverage of every documented behaviour and error), and
  * a differential layer (`test_matches_reference_*`) that runs the agent's
    program on many curated and deterministically-generated inputs and compares
    its output, byte-for-byte, against `ref_stratdl.analyze` — the authoritative
    Python reference bundled here under /tests (never copied into the image, so
    the agent cannot read it or precompute answers). Because the perfect model of
    a stratified program is a unique invariant, agreement is equivalent to both
    implementations being correct.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ref_stratdl import analyze  # noqa: E402

STRATDL = "/app/stratdl"
SRC = "/app/src/stratdl.pl"
EXAMPLES = "/app/examples"


def run(program: str, timeout: float = 30.0) -> tuple[int, str]:
    """Run /app/stratdl on `program` text; return (returncode, output_text)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dl", delete=False) as f:
        f.write(program)
        in_path = f.name
    out_path = in_path + ".out"
    try:
        proc = subprocess.run(
            [STRATDL, in_path, out_path], capture_output=True, text=True, timeout=timeout
        )
        try:
            with open(out_path) as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        return proc.returncode, text
    finally:
        for p in (in_path, out_path):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


# ─────────────────────────── facts / sorting ───────────────────────────
def test_facts_only_passthrough():
    rc, out = run("p(a).\np(b).\nq(c,d).\n")
    assert rc == 0
    assert out == "facts: 3\np(a)\np(b)\nq(c,d)\n", repr(out)


def test_canonical_sort_by_name_then_arity_then_args():
    rc, out = run("z(a).\na(b,c).\na(a,b).\nm(x).\n")
    assert rc == 0
    assert out == "facts: 4\na(a,b)\na(b,c)\nm(x)\nz(a)\n", repr(out)


def test_empty_program_has_empty_model():
    rc, out = run("% nothing here\n\n")
    assert rc == 0
    assert out == "facts: 0\n", repr(out)


def test_duplicate_facts_collapse():
    rc, out = run("p(a).\np(a).\np(a).\n")
    assert rc == 0
    assert out == "facts: 1\np(a)\n", repr(out)


# ─────────────────────────── recursion / joins ─────────────────────────
def test_transitive_closure():
    rc, out = run(
        "edge(a,b).\nedge(b,c).\npath(X,Y) :- edge(X,Y).\n"
        "path(X,Y) :- edge(X,Z), path(Z,Y).\n"
    )
    assert rc == 0
    assert out == (
        "facts: 5\nedge(a,b)\nedge(b,c)\npath(a,b)\npath(a,c)\npath(b,c)\n"
    ), repr(out)


def test_three_way_join():
    rc, out = run(
        "e(a,b).\ne(b,c).\ne(a,c).\ntri(X,Y,Z) :- e(X,Y), e(Y,Z), e(X,Z).\n"
    )
    assert rc == 0
    assert out == "facts: 4\ne(a,b)\ne(a,c)\ne(b,c)\ntri(a,b,c)\n", repr(out)


# ─────────────────────────── stratified negation ───────────────────────
def test_single_negation_layer():
    rc, out = run("p(a).\np(b).\nq(b).\nr(X) :- p(X), not q(X).\n")
    assert rc == 0
    assert out == "facts: 4\np(a)\np(b)\nq(b)\nr(a)\n", repr(out)


def test_two_negation_layers():
    rc, out = run(
        "base(a).\nbase(b).\np(a).\nq(X) :- base(X), not p(X).\n"
        "r(X) :- base(X), not q(X).\n"
    )
    assert rc == 0
    assert out == "facts: 5\nbase(a)\nbase(b)\np(a)\nq(b)\nr(a)\n", repr(out)


def test_closed_world_negation_of_empty_predicate():
    # `gone` is never asserted, so `not gone(X)` holds for every item.
    rc, out = run("item(a).\nitem(b).\navail(X) :- item(X), not gone(X).\n")
    assert rc == 0
    assert out == "facts: 4\navail(a)\navail(b)\nitem(a)\nitem(b)\n", repr(out)


def test_negation_literal_before_positive_binder():
    # The negated literal is written before the positive literal that binds X;
    # safety still holds and X must be ground when the negation is tested.
    rc, out = run("p(a).\np(b).\nq(b).\nr(X) :- not q(X), p(X).\n")
    assert rc == 0
    assert out == "facts: 4\np(a)\np(b)\nq(b)\nr(a)\n", repr(out)


# ───────────────────────────── line counting ───────────────────────────
def test_line_numbers_count_comments_and_blanks():
    rc, out = run("% c\n% c2\np(X).\n")
    assert rc == 1
    assert out.strip() == "Error: non-ground fact at line 3", repr(out)


# ───────────────────────────── error ladder ────────────────────────────
def test_malformed_missing_period():
    rc, out = run("p(a)\n")
    assert rc == 1
    assert out.strip() == "Error: malformed clause at line 1", repr(out)


def test_malformed_bad_token():
    rc, out = run("p(a) :- q(a) ; r(a).\n")
    assert rc == 1
    assert out.strip() == "Error: malformed clause at line 1", repr(out)


def test_malformed_unbalanced_paren():
    rc, out = run("p(a) :- q(a.\n")
    assert rc == 1
    assert out.strip() == "Error: malformed clause at line 1", repr(out)


def test_arity_mismatch_in_fact():
    rc, out = run("p(a).\np(a,b).\n")
    assert rc == 1
    assert out.strip() == "Error: arity mismatch for p at line 2", repr(out)


def test_arity_mismatch_in_rule_body():
    rc, out = run("p(a).\nq(X) :- p(X,Y).\n")
    assert rc == 1
    assert out.strip() == "Error: arity mismatch for p at line 2", repr(out)


def test_non_ground_fact():
    rc, out = run("p(X).\n")
    assert rc == 1
    assert out.strip() == "Error: non-ground fact at line 1", repr(out)


def test_unsafe_rule_head_variable():
    rc, out = run("p(X) :- q(a).\nq(a).\n")
    assert rc == 1
    assert out.strip() == "Error: unsafe rule at line 1", repr(out)


def test_unsafe_rule_negation_variable():
    rc, out = run("p(a) :- q(a), not r(X).\nq(a).\n")
    assert rc == 1
    assert out.strip() == "Error: unsafe rule at line 1", repr(out)


def test_program_not_stratifiable():
    rc, out = run("q(a).\np(X) :- q(X), not r(X).\nr(X) :- q(X), not p(X).\n")
    assert rc == 1
    assert out.strip() == "Error: program not stratifiable", repr(out)


def test_malformed_precedes_other_errors():
    # A structurally malformed line (line 1) is reported before the unsafe rule
    # on line 2, because the parse phase runs first.
    rc, out = run("p(a)\nq(X) :- r(a).\n")
    assert rc == 1
    assert out.strip() == "Error: malformed clause at line 1", repr(out)


def test_recursion_through_positive_cycle_is_fine():
    # A positive cycle (no negation) is stratifiable and must evaluate, not error.
    rc, out = run(
        "link(a,b).\nlink(b,a).\nsame(X,Y) :- link(X,Y).\n"
        "same(X,Y) :- link(X,Z), same(Z,Y).\n"
    )
    assert rc == 0
    assert out.splitlines()[0] == "facts: 6", repr(out)


# ───────────────────────────── anti-cheat ──────────────────────────────
def test_source_contains_no_escape_tokens():
    import re
    with open(SRC) as f:
        text = f.read()
    # drop %-comments so prose/identifiers don't false-trip
    src_nc = re.sub(r"%[^\n]*", "", text)
    for tok in ("system/1", "system/2", "exec/", "popen/", "socket_", "process_create"):
        assert tok not in src_nc, f"forbidden shell-out token {tok!r} found in source"
    # GNU Prolog FFI / C-bridge escapes (call-form, so legit identifiers are safe)
    for pat in (r"\bforeign\s*\(", r":-\s*foreign\b", r"\bforeign_file\s*\(", r"\bc_code\s*\("):
        assert not re.search(pat, src_nc), f"forbidden FFI escape {pat!r} found in source"


# ────────────────── differential against the reference ─────────────────
_CURATED = [
    "p(a).\n",
    "p(a).\np(b).\nq(c,d).\n",
    "edge(a,b).\nedge(b,c).\npath(X,Y) :- edge(X,Y).\npath(X,Y) :- edge(X,Z), path(Z,Y).\n",
    "p(a).\np(b).\nq(b).\nr(X) :- p(X), not q(X).\n",
    "base(a).\nbase(b).\np(a).\nq(X) :- base(X), not p(X).\nr(X) :- base(X), not q(X).\n",
    "item(a).\nitem(b).\navail(X) :- item(X), not gone(X).\n",
    "e(a,b).\ne(b,c).\ne(a,c).\ntri(X,Y,Z) :- e(X,Y), e(Y,Z), e(X,Z).\n",
    "link(a,b).\nlink(b,a).\nsame(X,Y) :- link(X,Y).\nsame(X,Y) :- link(X,Z), same(Z,Y).\n",
    "% empty model\nq(X) :- p(X).\np(a).\n",
    "% errors:\n",
    "p(X).\n",
    "p(a).\np(a,b).\n",
    "p(X) :- q(a).\nq(a).\n",
    "p(a) :- q(a), not r(X).\nq(a).\n",
    "q(a).\np(X) :- q(X), not r(X).\nr(X) :- q(X), not p(X).\n",
    "p(a)\n",
    "p(a) :- .\n",
    "p(a) :- q(a) ; r(a).\n",
    "z(a).\na(b,c).\na(a,b).\nm(x).\n",
    "n(a).\nn(b).\nn(c).\nodd(X) :- n(X), not even(X).\neven(a).\n",
]


def test_matches_reference_on_curated_programs():
    for s in _CURATED:
        rc, out = run(s)
        exp = analyze(s)
        assert out == exp, f"output mismatch for {s!r}: got {out!r} want {exp!r}"
        assert rc == (1 if exp.startswith("Error:") else 0), (s, rc, exp)


# ── deterministic generators (the agent never sees these exact programs) ──
_CONSTS = ["a", "b", "c", "d"]
_VARS = ["X", "Y", "Z", "W"]
_PREDS = ["p", "q", "r", "s", "e", "t"]


def _gen_program(rng: random.Random) -> str:
    consts = _CONSTS[: rng.randint(2, 4)]
    preds = _PREDS[: rng.randint(2, 5)]
    arity = {p: rng.randint(1, 2) for p in preds}
    lines = []
    for _ in range(rng.randint(1, 6)):
        p = rng.choice(preds)
        lines.append(f"{p}({','.join(rng.choice(consts) for _ in range(arity[p]))}).")
    for _ in range(rng.randint(1, 5)):
        head = rng.choice(preds)
        used = _VARS[: rng.randint(1, 3)]
        lits = []
        for j in range(rng.randint(1, 3)):
            bp = rng.choice(preds)
            neg = j > 0 and rng.random() < 0.35
            terms = [rng.choice(used) if rng.random() < 0.6 else rng.choice(consts)
                     for _ in range(arity[bp])]
            lits.append(("not " if neg else "") + f"{bp}({','.join(terms)})")
        posvars = set()
        for lit in lits:
            if lit.startswith("not "):
                continue
            for tk in lit[lit.index("(") + 1:-1].split(","):
                if tk and tk[0].isupper():
                    posvars.add(tk)
        hterms = [rng.choice(sorted(posvars)) if posvars and rng.random() < 0.8
                  else rng.choice(consts) for _ in range(arity[head])]
        lines.append(f"{head}({','.join(hterms)}) :- {', '.join(lits)}.")
    rng.shuffle(lines)
    if rng.random() < 0.4:
        lines.insert(rng.randint(0, len(lines)), "% comment")
    return "\n".join(lines) + "\n"


def _gen_arity(rng: random.Random) -> str:
    preds = _PREDS[: rng.randint(2, 4)]
    consts = _CONSTS[: rng.randint(2, 3)]
    lines = []
    for _ in range(rng.randint(2, 6)):
        p = rng.choice(preds)
        k = rng.randint(1, 3)
        args = [rng.choice(consts) for _ in range(k)]
        lines.append(f"{p}({','.join(args)}).")
    return "\n".join(lines) + "\n"


def _gen_messy(rng: random.Random) -> str:
    pool = ["p(a).", "q(X) :- p(X).", "r(a,b).", "p(a)", "p(a) :- .",
            "q(X).", ":- p(a).", "p(a) :- q(X).", "p(,).", "p(a,).",
            "P(a).", "p(A).", "not p(a).", "p(a) : - q(a).", "p (a).", "p(a))."]
    return "\n".join(rng.choice(pool) for _ in range(rng.randint(1, 5))) + "\n"


def test_matches_reference_on_generated_programs():
    """Deterministically-generated programs the agent never sees: a hardcoded or
    example-specific implementation cannot match the reference on all of them."""
    rng = random.Random(20260614)
    mism = 0
    checked = 0
    for _ in range(90):
        s = _gen_program(rng)
        checked += 1
        rc, out = run(s)
        exp = analyze(s)
        if out != exp or rc != (1 if exp.startswith("Error:") else 0):
            mism += 1
            if mism <= 3:
                print(f"program {s!r}\n got {out!r}\n exp {exp!r}")
    assert mism == 0, f"{mism}/{checked} generated programs mismatched the reference"


def test_matches_reference_on_generated_arity_and_messy():
    rng = random.Random(7788)
    mism = 0
    checked = 0
    for _ in range(80):
        s = _gen_arity(rng) if rng.random() < 0.5 else _gen_messy(rng)
        checked += 1
        rc, out = run(s)
        exp = analyze(s)
        if out != exp or rc != (1 if exp.startswith("Error:") else 0):
            mism += 1
            if mism <= 3:
                print(f"input {s!r}\n got {out!r}\n exp {exp!r}")
    assert mism == 0, f"{mism}/{checked} generated inputs mismatched the reference"


# ───────────────────────────── example fixtures ────────────────────────
def test_shipped_examples_match_reference():
    for name in sorted(os.listdir(EXAMPLES)):
        if not name.endswith(".dl"):
            continue
        with open(os.path.join(EXAMPLES, name)) as f:
            program = f.read()
        rc, out = run(program)
        exp = analyze(program)
        assert out == exp, f"{name}: got {out!r} want {exp!r}"
        assert rc == (1 if exp.startswith("Error:") else 0), name

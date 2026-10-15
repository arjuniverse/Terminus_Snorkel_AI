"""Authoritative reference semantics for stratdl-gp.

Evaluates a stratified Datalog program to its unique perfect (minimal) model and
renders the model as canonical text, exactly per the binding spec.

Pipeline:
  1. tokenize + parse every clause (single error, first encountered, with line)
  2. global arity-consistency check
  3. per-clause safety / ground-fact check
  4. predicate dependency graph -> stratification (longest-path relaxation; a
     negative edge inside a cycle => not stratifiable)
  5. stratum-by-stratum naive fixpoint with closed-world negation
  6. canonical emit: `facts: <N>` then every model fact sorted by
     (predicate, arity, args).

The perfect model of a stratified program is unique and independent of the
chosen stratification, so analyze(text) is a function of the program's meaning
alone — the GNU-Prolog oracle must reproduce it byte-for-byte, and agreement
under differential fuzzing is equivalent to both being correct.
"""
from __future__ import annotations

# ───────────────────────────── error type ──────────────────────────────
class ProgError(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg


# ───────────────────────────── tokenizer ───────────────────────────────
# Tokens for one clause (the trailing '.' already removed by the caller):
#   '(' ')' ',' ':-' 'not'(kw) IDENT VAR
# IDENT = [a-z][A-Za-z0-9_]* ; VAR = [A-Z][A-Za-z0-9_]*
def _is_ident_start(c): return "a" <= c <= "z"
def _is_var_start(c): return "A" <= c <= "Z"
def _is_ident_char(c): return c.isalnum() or c == "_"


def _tokenize(s: str):
    """Tokenize a clause body string. Raise ProgError('malformed') on any bad
    character. Returns a list of (kind, value) tokens."""
    toks = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t":
            i += 1
            continue
        if c == "(":
            toks.append(("lp", "("))
            i += 1
            continue
        if c == ")":
            toks.append(("rp", ")"))
            i += 1
            continue
        if c == ",":
            toks.append(("comma", ","))
            i += 1
            continue
        if c == ":" and i + 1 < n and s[i + 1] == "-":
            toks.append(("neck", ":-"))
            i += 2
            continue
        if _is_ident_start(c):
            j = i + 1
            while j < n and _is_ident_char(s[j]):
                j += 1
            word = s[i:j]
            if word == "not":
                toks.append(("kw_not", word))
            else:
                toks.append(("ident", word))
            i = j
            continue
        if _is_var_start(c):
            j = i + 1
            while j < n and _is_ident_char(s[j]):
                j += 1
            toks.append(("var", s[i:j]))
            i = j
            continue
        raise ProgError("malformed")
    return toks


# ───────────────────────────── parser ──────────────────────────────────
# Returns a clause dict:
#   {"head": atom, "body": [lit, ...]}
# atom  = ("pred", name, (term, ...))    term = ("c", name) | ("v", name)
# lit   = ("pos", atom) | ("neg", atom)
class _P:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else ("eof", "")

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, kind):
        if self.peek()[0] != kind:
            raise ProgError("malformed")
        return self.take()

    def atom(self):
        if self.peek()[0] != "ident":
            raise ProgError("malformed")
        name = self.take()[1]
        self.expect("lp")
        terms = [self.term()]
        while self.peek()[0] == "comma":
            self.take()
            terms.append(self.term())
        self.expect("rp")
        return ("pred", name, tuple(terms))

    def term(self):
        k = self.peek()[0]
        if k == "ident":
            return ("c", self.take()[1])
        if k == "var":
            return ("v", self.take()[1])
        raise ProgError("malformed")

    def literal(self):
        if self.peek()[0] == "kw_not":
            self.take()
            return ("neg", self.atom())
        return ("pos", self.atom())

    def clause(self):
        head = self.atom()
        body = []
        if self.peek()[0] == "neck":
            self.take()
            body.append(self.literal())
            while self.peek()[0] == "comma":
                self.take()
                body.append(self.literal())
        if self.peek()[0] != "eof":
            raise ProgError("malformed")
        return {"head": head, "body": body}


def _parse_clause(text: str):
    """Parse one clause string (without trailing '.'). Raise ProgError('malformed')."""
    toks = _tokenize(text)
    if not toks:
        raise ProgError("malformed")
    return _P(toks).clause()


# ───────────────────────────── front end ───────────────────────────────
def _clauses_with_lines(src: str):
    """Yield (lineno, clause_text_without_dot) for each non-blank, non-comment
    line. lineno is 1-based over RAW file lines. Raises ProgError('malformed
    clause at line N') on the first structurally bad line."""
    out = []
    for idx, raw in enumerate(src.split("\n"), start=1):
        line = raw
        # strip a comment: '%' to end of line
        h = line.find("%")
        if h != -1:
            line = line[:h]
        line = line.strip()
        if line == "":
            continue
        if not line.endswith("."):
            raise ProgError(f"malformed clause at line {idx}")
        body = line[:-1].strip()
        if body == "":
            raise ProgError(f"malformed clause at line {idx}")
        try:
            cl = _parse_clause(body)
        except ProgError:
            raise ProgError(f"malformed clause at line {idx}")
        out.append((idx, cl))
    return out


def _atoms_of(cl):
    """All atoms in a clause: head first, then body literals in order."""
    yield cl["head"]
    for (_pol, a) in cl["body"]:
        yield a


def analyze(src: str) -> str:
    """Compute the canonical model text, or 'Error: <reason>\\n'."""
    try:
        return _analyze(src)
    except ProgError as e:
        return f"Error: {e.msg}\n"


def _analyze(src: str) -> str:
    clauses = _clauses_with_lines(src)  # phase 1: structural parse

    # phase 2: global arity consistency (scan atoms in line order, head then body)
    arity = {}
    for (ln, cl) in clauses:
        for a in _atoms_of(cl):
            _pred, name, terms = a
            k = len(terms)
            if name in arity:
                if arity[name] != k:
                    raise ProgError(f"arity mismatch for {name} at line {ln}")
            else:
                arity[name] = k

    # phase 3: safety / ground-fact (per clause, top to bottom)
    for (ln, cl) in clauses:
        body = cl["body"]
        if not body:
            # fact: must be ground
            if any(t[0] == "v" for t in cl["head"][2]):
                raise ProgError(f"non-ground fact at line {ln}")
            continue
        # positive-body variables
        posvars = set()
        for (pol, a) in body:
            if pol == "pos":
                for t in a[2]:
                    if t[0] == "v":
                        posvars.add(t[1])
        # head vars
        for t in cl["head"][2]:
            if t[0] == "v" and t[1] not in posvars:
                raise ProgError(f"unsafe rule at line {ln}")
        # negative-literal vars
        for (pol, a) in body:
            if pol == "neg":
                for t in a[2]:
                    if t[0] == "v" and t[1] not in posvars:
                        raise ProgError(f"unsafe rule at line {ln}")

    # phase 4: stratification via longest-path relaxation
    preds = sorted(arity)
    rules = [cl for (_ln, cl) in clauses if cl["body"]]
    # edges: list of (src_pred, dst_pred, neg?)
    edges = []
    for cl in rules:
        h = cl["head"][1]
        for (pol, a) in cl["body"]:
            edges.append((a[1], h, pol == "neg"))
    stratum = {p: 0 for p in preds}
    npred = len(preds)
    changed = True
    rounds = 0
    while changed:
        changed = False
        rounds += 1
        for (b, hh, neg) in edges:
            want = stratum[b] + (1 if neg else 0)
            if want > stratum[hh]:
                stratum[hh] = want
                changed = True
        if rounds > npred + 1:
            # a negative edge keeps growing inside a cycle
            raise ProgError("program not stratifiable")

    maxs = max(stratum.values()) if stratum else 0

    # phase 5: stratum-by-stratum naive fixpoint
    # model: dict pred -> set of arg-tuples (tuple of constant strings)
    model = {p: set() for p in preds}
    # seed EDB facts (facts go in immediately; their pred's stratum is 0 by
    # construction unless it also appears as a rule head, which is fine)
    for (_ln, cl) in clauses:
        if not cl["body"]:
            name = cl["head"][1]
            tup = tuple(t[1] for t in cl["head"][2])
            model[name].add(tup)

    rules_by_stratum = {}
    for cl in rules:
        s = stratum[cl["head"][1]]
        rules_by_stratum.setdefault(s, []).append(cl)

    for s in range(0, maxs + 1):
        srules = rules_by_stratum.get(s, [])
        if not srules:
            continue
        while True:
            added = False
            for cl in srules:
                for newfact in _derive(cl, model):
                    name = cl["head"][1]
                    if newfact not in model[name]:
                        model[name].add(newfact)
                        added = True
            if not added:
                break

    # phase 6: canonical emit
    facts = []
    for name in preds:
        for tup in model[name]:
            facts.append((name, len(tup), tup))
    facts.sort()
    lines = [f"facts: {len(facts)}"]
    for (name, _k, tup) in facts:
        lines.append(f"{name}({','.join(tup)})")
    return "\n".join(lines) + "\n"


def _derive(cl, model):
    """Yield ground head tuples derivable from this rule under the current model
    (one pass). All POSITIVE literals are joined first (binding the variables),
    then NEGATIVE literals are checked closed-world; safety guarantees every
    negative-literal and head variable is bound by some positive literal."""
    return _derive_split(cl, model, model)


def _apply(term, subst):
    if term[0] == "c":
        return term[1]
    return subst[term[1]]


# ───────────────────────── independent model checker ────────────────────
# Ground-truth validator used only in dev: confirm `analyze`'s model is a
# supported model of the program (every rule satisfied; every derived fact
# supported). Proves the reference itself, independent of the algorithm.
def check_model(src: str):
    clauses = _clauses_with_lines(src)
    arity = {}
    for (_ln, cl) in clauses:
        for a in _atoms_of(cl):
            arity.setdefault(a[1], len(a[2]))
    model = {p: set() for p in arity}
    # parse the analyze() output back into a model
    out = _analyze(src)
    for line in out.splitlines()[1:]:
        nm = line[:line.index("(")]
        args = tuple(line[line.index("(") + 1:-1].split(",")) if line[line.index("(") + 1:-1] else ()
        model.setdefault(nm, set()).add(args)
    # 1) every fact present
    for (_ln, cl) in clauses:
        if not cl["body"]:
            tup = tuple(t[1] for t in cl["head"][2])
            assert tup in model[cl["head"][1]], ("fact missing", cl)
    # 2) closure: applying any rule yields nothing new (model is closed)
    for (_ln, cl) in clauses:
        if cl["body"]:
            for tup in _derive(cl, model):
                assert tup in model[cl["head"][1]], ("rule not closed", cl, tup)
    # 3) support: the founded set (positives derived bottom-up, negatives checked
    #    against the final model) must equal the model exactly.
    founded = {p: set() for p in model}
    for (_ln, cl) in clauses:
        if not cl["body"]:
            founded[cl["head"][1]].add(tuple(t[1] for t in cl["head"][2]))
    rules = [cl for (_ln, cl) in clauses if cl["body"]]
    changed = True
    while changed:
        changed = False
        for cl in rules:
            for tup in _derive_split(cl, founded, model):
                if tup not in founded[cl["head"][1]]:
                    founded[cl["head"][1]].add(tup)
                    changed = True
    for nm in model:
        assert founded[nm] == model[nm], ("support mismatch", nm,
                                          model[nm] ^ founded[nm])
    return True


def _derive_split(cl, posmodel, negmodel):
    """Join all positive literals against posmodel (binding variables), then
    filter by negative literals checked closed-world against negmodel. Positives
    are evaluated in clause order; negatives are checked only once every variable
    is bound (safety guarantees this)."""
    pos = [a for (pol, a) in cl["body"] if pol == "pos"]
    neg = [a for (pol, a) in cl["body"] if pol == "neg"]
    results = []

    def rec(idx, subst):
        if idx == len(pos):
            for a in neg:
                tup = tuple(_apply(t, subst) for t in a[2])
                if tup in negmodel.get(a[1], set()):
                    return
            results.append(tuple(_apply(t, subst) for t in cl["head"][2]))
            return
        name, terms = pos[idx][1], pos[idx][2]
        for tup in posmodel.get(name, ()):
            if len(tup) != len(terms):
                continue
            s2 = dict(subst)
            ok = True
            for t, val in zip(terms, tup):
                if t[0] == "c":
                    if t[1] != val:
                        ok = False
                        break
                elif t[1] in s2:
                    if s2[t[1]] != val:
                        ok = False
                        break
                else:
                    s2[t[1]] = val
            if ok:
                rec(idx + 1, s2)

    rec(0, {})
    return results


if __name__ == "__main__":
    import sys
    print(analyze(sys.stdin.read()), end="")

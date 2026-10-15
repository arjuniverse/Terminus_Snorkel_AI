% stratdl — stratified Datalog evaluator (reference oracle).
%
% run(InputPath, OutputPath): read a Datalog program, compute its unique perfect
% (minimal) model, and write the canonical model text to OutputPath; on any
% error write a single `Error: <reason>` line. halt(0) on success, halt(1) on
% error.

:- dynamic(mfact/2).

% ───────────────────────────── entry point ─────────────────────────────
run(In, Out) :-
    catch(run_ok(In, Out), err(M), run_err(Out, M)).

run_ok(In, Out) :-
    read_program(In, Lines),
    parse_all(Lines, Clauses),
    check_arity(Clauses),
    check_safety(Clauses),
    all_preds(Clauses, Preds),
    length(Preds, NP),
    build_edges(Clauses, Edges),
    init_strata(Preds, S0),
    relax_loop(Edges, S0, Strata, 0, NP),
    max_stratum(Strata, MaxS),
    eval(Clauses, Strata, MaxS),
    emit(Out).

run_err(Out, M) :-
    open(Out, write, S),
    format(S, "Error: ~w~n", [M]),
    close(S),
    halt(1).

% ───────────────────────────── read + split ────────────────────────────
read_program(In, Lines) :-
    open(In, read, S),
    read_all(S, Codes),
    close(S),
    split_nl(Codes, Raw),
    process_lines(Raw, 1, Lines).

read_all(S, Codes) :-
    get_code(S, C),
    ( C == -1 -> Codes = []
    ; Codes = [C|T], read_all(S, T) ).

split_nl(Codes, Lines) :- split_nl_(Codes, [], Lines).
split_nl_([], Cur, [Line]) :- reverse(Cur, Line).
split_nl_([10|T], Cur, [Line|Lines]) :- !, reverse(Cur, Line), split_nl_(T, [], Lines).
split_nl_([C|T], Cur, Lines) :- split_nl_(T, [C|Cur], Lines).

process_lines([], _, []).
process_lines([Raw|Rest], Ln, Out) :-
    strip_comment(Raw, NoCmt),
    trim(NoCmt, Trimmed),
    Ln1 is Ln + 1,
    ( Trimmed == [] -> process_lines(Rest, Ln1, Out)
    ; Out = [ln(Ln, Trimmed)|Out1], process_lines(Rest, Ln1, Out1) ).

strip_comment([], []).
strip_comment([37|_], []) :- !.            % 37 = '%'
strip_comment([C|T], [C|R]) :- strip_comment(T, R).

trim(Codes, Out) :-
    drop_ws(Codes, C1), reverse(C1, R1),
    drop_ws(R1, R2), reverse(R2, Out).
drop_ws([C|T], Out) :- ws(C), !, drop_ws(T, Out).
drop_ws(L, L).
ws(9). ws(13). ws(32).

% ───────────────────────────── parser ──────────────────────────────────
parse_all([], []).
parse_all([ln(Ln, Codes)|R], [cl(Ln, Clause)|R2]) :-
    ( append(Body0, [46], Codes) -> true       % 46 = '.'
    ; line_msg('malformed clause', Ln, M0), throw(err(M0)) ),
    trim(Body0, Body1),
    ( Body1 == [] -> line_msg('malformed clause', Ln, M1), throw(err(M1)) ; true ),
    catch( ( tokenize(Body1, Toks), parse_clause(Toks, Clause) ),
           malformed,
           ( line_msg('malformed clause', Ln, M2), throw(err(M2)) ) ),
    parse_all(R, R2).

tokenize([], []).
tokenize([C|Cs], Toks) :-
    ( (C =:= 32 ; C =:= 9) -> tokenize(Cs, Toks)
    ; C =:= 0'( -> Toks = [lp|T], tokenize(Cs, T)
    ; C =:= 0') -> Toks = [rp|T], tokenize(Cs, T)
    ; C =:= 0', -> Toks = [comma|T], tokenize(Cs, T)
    ; ( C =:= 0': , Cs = [0'-|Cs2] ) -> Toks = [neck|T], tokenize(Cs2, T)
    ; ident_start(C) -> take_ident([C|Cs], Word, Rest),
          ( Word == not -> Toks = [kw_not|T] ; Toks = [id(Word)|T] ),
          tokenize(Rest, T)
    ; var_start(C) -> take_ident([C|Cs], Word, Rest),
          Toks = [var(Word)|T], tokenize(Rest, T)
    ; throw(malformed) ).

ident_start(C) :- C >= 0'a, C =< 0'z.
var_start(C)   :- C >= 0'A, C =< 0'Z.
ident_char(C) :- ( C >= 0'a, C =< 0'z ) ; ( C >= 0'A, C =< 0'Z ) ;
                 ( C >= 0'0, C =< 0'9 ) ; C =:= 0'_.

take_ident(Codes, Atom, Rest) :- take_ident_(Codes, IC, Rest), atom_codes(Atom, IC).
take_ident_([C|Cs], [C|IC], Rest) :- ident_char(C), !, take_ident_(Cs, IC, Rest).
take_ident_(Cs, [], Cs).

% clause := atom [ ':-' literal (',' literal)* ] (end)
parse_clause(Toks, clause(Head, Body)) :-
    p_atom(Toks, Head, R1),
    ( R1 = [neck|R2] -> p_body(R2, Body, R3) ; Body = [], R3 = R1 ),
    ( R3 == [] -> true ; throw(malformed) ).

p_atom([id(Name), lp|R1], pred(Name, Args), R) :- !, p_terms(R1, Args, R).
p_atom(_, _, _) :- throw(malformed).

p_terms(Toks, [T|Ts], Rest) :- p_term(Toks, T, R1), p_terms_rest(R1, Ts, Rest).
p_terms_rest([comma|R], [T|Ts], Rest) :- !, p_term(R, T, R1), p_terms_rest(R1, Ts, Rest).
p_terms_rest([rp|R], [], R) :- !.
p_terms_rest(_, _, _) :- throw(malformed).

p_term([id(N)|R], c(N), R) :- !.
p_term([var(N)|R], v(N), R) :- !.
p_term(_, _, _) :- throw(malformed).

p_body(Toks, [Lit|Lits], Rest) :-
    p_lit(Toks, Lit, R1),
    ( R1 = [comma|R2] -> p_body(R2, Lits, Rest) ; Lits = [], Rest = R1 ).
p_lit([kw_not|R0], neg(A), R) :- !, p_atom(R0, A, R).
p_lit(Toks, pos(A), R) :- p_atom(Toks, A, R).

% ───────────────────────────── arity check ─────────────────────────────
check_arity(Clauses) :- check_arity_(Clauses, []).
check_arity_([], _).
check_arity_([cl(Ln, C)|R], Seen) :-
    atoms_in(C, Atoms),
    check_atoms_arity(Atoms, Ln, Seen, Seen1),
    check_arity_(R, Seen1).
check_atoms_arity([], _, S, S).
check_atoms_arity([pred(N, Args)|R], Ln, S, Sout) :-
    length(Args, K),
    ( member(N-K0, S)
      -> ( K0 =:= K -> S1 = S
         ; atom_concat('arity mismatch for ', N, P0), line_msg(P0, Ln, M), throw(err(M)) )
    ; S1 = [N-K|S] ),
    check_atoms_arity(R, Ln, S1, Sout).

atoms_in(clause(Head, Body), [Head|BodyAtoms]) :- body_atoms(Body, BodyAtoms).
body_atoms([], []).
body_atoms([pos(A)|R], [A|R2]) :- body_atoms(R, R2).
body_atoms([neg(A)|R], [A|R2]) :- body_atoms(R, R2).

% ───────────────────────────── safety check ────────────────────────────
check_safety([]).
check_safety([cl(Ln, clause(Head, Body))|R]) :-
    ( Body == [] ->
        ( head_has_var(Head) -> line_msg('non-ground fact', Ln, M), throw(err(M)) ; true )
    ; posvars(Body, PV),
      headvars(Head, HV),
      ( subset_vars(HV, PV) -> true ; line_msg('unsafe rule', Ln, M1), throw(err(M1)) ),
      negvars(Body, NV),
      ( subset_vars(NV, PV) -> true ; line_msg('unsafe rule', Ln, M2), throw(err(M2)) ) ),
    check_safety(R).

head_has_var(pred(_, Args)) :- member(v(_), Args).
headvars(pred(_, Args), Vs) :- term_vars_list(Args, Vs).
term_vars_list([], []).
term_vars_list([c(_)|R], V) :- term_vars_list(R, V).
term_vars_list([v(N)|R], [N|V]) :- term_vars_list(R, V).
posvars(Body, Vs) :- findall(N, (member(pos(pred(_, A)), Body), member(v(N), A)), L), sort(L, Vs).
negvars(Body, Vs) :- findall(N, (member(neg(pred(_, A)), Body), member(v(N), A)), L), sort(L, Vs).
subset_vars(Sub, Super) :- forall(member(X, Sub), member(X, Super)).

% ───────────────────────────── stratification ──────────────────────────
all_preds(Clauses, Preds) :-
    findall(N, (member(cl(_, C), Clauses), atoms_in(C, As), member(pred(N, _), As)), L),
    sort(L, Preds).

build_edges(Clauses, Edges) :-
    findall(edge(B, H, Neg),
        ( member(cl(_, clause(pred(H, _), Body)), Clauses), Body \== [],
          member(Lit, Body), lit_pred_neg(Lit, B, Neg) ),
        Edges).
lit_pred_neg(pos(pred(B, _)), B, 0).
lit_pred_neg(neg(pred(B, _)), B, 1).

init_strata([], []).
init_strata([N|R], [N-0|R2]) :- init_strata(R, R2).

relax_loop(Edges, S, Sout, Rounds, NP) :-
    R1 is Rounds + 1,
    relax_pass(Edges, S, S1, Changed),
    Lim is NP + 1,
    ( R1 > Lim -> throw(err('program not stratifiable')) ; true ),
    ( Changed == true -> relax_loop(Edges, S1, Sout, R1, NP) ; Sout = S1 ).

relax_pass([], S, S, false).
relax_pass([edge(B, H, Neg)|Es], Sin, Sout, Changed) :-
    getstr(B, Sin, SB), getstr(H, Sin, SH), Want is SB + Neg,
    ( Want > SH -> setstr(H, Want, Sin, Smid), relax_pass(Es, Smid, Sout, _), Changed = true
    ; relax_pass(Es, Sin, Sout, Changed) ).

getstr(N, [N0-V|R], Out) :- ( N == N0 -> Out = V ; getstr(N, R, Out) ).
setstr(N, V, [N0-V0|R], Out) :-
    ( N == N0 -> Out = [N0-V|R] ; Out = [N0-V0|R2], setstr(N, V, R, R2) ).

max_stratum(Strata, Max) :- findall(V, member(_-V, Strata), Vs), max_or0(Vs, 0, Max).
max_or0([], M, M).
max_or0([H|T], A, M) :- ( H > A -> max_or0(T, H, M) ; max_or0(T, A, M) ).

% ───────────────────────────── evaluation ──────────────────────────────
eval(Clauses, Strata, MaxS) :-
    retractall(mfact(_, _)),
    seed_facts(Clauses),
    build_rules(Clauses, Strata, Rules),
    eval_strata(0, MaxS, Rules).

seed_facts([]).
seed_facts([cl(_, clause(pred(N, Args), []))|R]) :- !,
    terms_to_atoms(Args, AA),
    ( mfact(N, AA) -> true ; assertz(mfact(N, AA)) ),
    seed_facts(R).
seed_facts([_|R]) :- seed_facts(R).
terms_to_atoms([], []).
terms_to_atoms([c(N)|R], [N|R2]) :- terms_to_atoms(R, R2).

build_rules(Clauses, Strata, Rules) :-
    findall(rule(SH, E),
        ( member(cl(_, clause(pred(HN, HA), Body)), Clauses), Body \== [],
          getstr(HN, Strata, SH),
          to_eval(clause(pred(HN, HA), Body), E) ),
        Rules).

to_eval(clause(pred(HN, HArgs), Body), e(HN, EHArgs, Pos, Neg)) :-
    conv_terms(HArgs, EHArgs, [], M1),
    conv_lits(Body, M1, _, Pos, Neg).
conv_term(c(N), N, M, M).
conv_term(v(N), Var, M, M) :- member(N-Var, M), !.
conv_term(v(N), Var, M, [N-Var|M]).
conv_terms([], [], M, M).
conv_terms([T|Ts], [E|Es], M0, M) :- conv_term(T, E, M0, M1), conv_terms(Ts, Es, M1, M).
conv_atom(pred(N, Args), lit(N, EArgs), M0, M) :- conv_terms(Args, EArgs, M0, M).
conv_lits([], M, M, [], []).
conv_lits([pos(A)|R], M0, M, [EA|Pos], Neg) :- conv_atom(A, EA, M0, M1), conv_lits(R, M1, M, Pos, Neg).
conv_lits([neg(A)|R], M0, M, Pos, [EA|Neg]) :- conv_atom(A, EA, M0, M1), conv_lits(R, M1, M, Pos, Neg).

eval_strata(S, MaxS, _) :- S > MaxS, !.
eval_strata(S, MaxS, Rules) :- fixpoint(Rules, S), S1 is S + 1, eval_strata(S1, MaxS, Rules).
fixpoint(Rules, S) :-
    apply_all(Rules, S, false, Changed),
    ( Changed == true -> fixpoint(Rules, S) ; true ).
apply_all([], _, C, C).
apply_all([rule(SH, E)|R], S, Cin, Cout) :-
    ( SH =:= S -> apply_rule(E, Cin, Cmid) ; Cmid = Cin ),
    apply_all(R, S, Cmid, Cout).
apply_rule(E, Cin, Cout) :-
    findall(N-Args, derive(E, N, Args), Heads),
    assert_heads(Heads, Cin, Cout).
derive(e(HN, EHArgs, Pos, Neg), HN, HArgs) :-
    copy_term(e(HN, EHArgs, Pos, Neg), e(HN, EH2, Pos2, Neg2)),
    match_pos(Pos2),
    check_neg(Neg2),
    HArgs = EH2.
match_pos([]).
match_pos([lit(N, Args)|R]) :- mfact(N, Args), match_pos(R).
check_neg([]).
check_neg([lit(N, Args)|R]) :- \+ mfact(N, Args), check_neg(R).
assert_heads([], C, C).
assert_heads([N-Args|R], Cin, Cout) :-
    ( mfact(N, Args) -> Cmid = Cin ; assertz(mfact(N, Args)), Cmid = true ),
    assert_heads(R, Cmid, Cout).

% ───────────────────────────── emit ────────────────────────────────────
emit(Out) :-
    findall(k(N, K, Args), (mfact(N, Args), length(Args, K)), Keys0),
    sort(Keys0, Keys),
    length(Keys, NFacts),
    open(Out, write, S),
    format(S, "facts: ~w~n", [NFacts]),
    emit_facts(Keys, S),
    close(S),
    halt(0).
emit_facts([], _).
emit_facts([k(N, _K, Args)|R], S) :-
    join_atoms(Args, ArgsStr),
    format(S, "~w(~w)~n", [N, ArgsStr]),
    emit_facts(R, S).
join_atoms([A], A) :- !.
join_atoms([A|R], Out) :- join_atoms(R, RS), atom_concat(A, ',', AC), atom_concat(AC, RS, Out).

% ───────────────────────────── helpers ─────────────────────────────────
line_msg(Prefix, Ln, Msg) :-
    number_codes(Ln, LnC), atom_codes(LnA, LnC),
    atom_concat(Prefix, ' at line ', P1),
    atom_concat(P1, LnA, Msg).

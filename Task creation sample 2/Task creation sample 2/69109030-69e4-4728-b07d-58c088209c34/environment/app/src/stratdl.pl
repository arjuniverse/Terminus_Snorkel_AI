% stratdl — stratified Datalog perfect-model evaluator.
%
% Implement `run/2` (and whatever helpers it needs) so the wrapper reads a
% Datalog program from InputPath, computes the program's unique perfect (minimal)
% model, and writes the canonical model report to OutputPath. The full input
% grammar, the stratification rules, the evaluation semantics, the parse-error
% ladder, and the exact output format are specified in /app/datalog.md — that
% document is the binding contract and the report is graded byte-for-byte.
%
% Keep everything inside GNU Prolog: no shell-outs or external interpreters (the
% verifier rejects sources containing the tokens listed in the anti-cheat
% section of the spec). You may add helpers here or split logic across more .pl
% files and consult them, but leave run/2 in this file as the public entry point
% so the /app/stratdl driver finds it.
%
% NOTE: GNU Prolog's default `double_quotes` flag is `codes`, so a literal like
% "abc" is the code list [0'a,0'b,0'c]; that is often handy for character work.

% Public entry point. Read the program at InputPath, evaluate it, and write the
% report to OutputPath. On success write the model and halt(0); on any error
% write a single `Error: <reason>` line and halt(1).
run(_InputPath, _OutputPath) :-
    halt(1).

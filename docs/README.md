# How the solver works

`main` validates the input, calls `solve_grid`, and writes the penalty and grid.
The input must have positive dimensions with at most 100,000 cells. Invalid input
is reported on stderr with exit code 2.

`solve_grid` gets a fully lit, nonconflicting board from `greedy_fallback` and
scores it with `count_violations`. A zero penalty is already optimal. Otherwise,
`build_formula` encodes the puzzle and `solve_constraints` starts a fresh
`ConstraintSearch` for each tested penalty budget. Search tries zero first, then
uses binary search between the lower bound and the best known score.

## The five search components

| Component | Code | Purpose |
| --- | --- | --- |
| Unit propagation | `ConstraintSearch.propagate` | Force remaining literals when a constraint's slack reaches zero. |
| Branching | `ConstraintSearch.solve`, `prioritize_conflict` | Choose an unknown variable using a heap of conflict priorities; reuse its saved value, initially False. |
| Backtracking | `ConstraintSearch.backtrack` | Undo trail entries above the backjump level, restore slack, and return variables to the heap. |
| Clause learning | `ConstraintSearch.analyze_conflict`, `learn_clause` | Resolve explanations to a FirstUIP clause, then index it for later propagation. |
| Satisfiability checks | `ConstraintSearch.propagate`, `solve` | Detect conflicts, return `None` for a root-level conflict, or return a complete assignment when no unknowns remain. |

FirstUIP resolution leaves one literal at the conflict's highest decision level.
The search jumps back to the highest level among the other literals, where the
learned clause forces its remaining literal. Learned clauses follow from the
formula's explaining clauses; caller-supplied assumptions remain in explanations.
Learning stays local to one budget search because a looser budget can change which
clauses follow from the formula.

## Encoding and runtime

Each white cell has a bulb variable. Horizontal and vertical white-cell segments
allow at most one bulb, and illumination constraints require a visible bulb for
every white cell. Each numbered clue has a relaxation variable permitting its
violation. A budget constraint limits the number of relaxed clues; the returned
score counts actual clue mismatches.

An at-least-K constraint stores literal occurrences and a minimum. Its slack is
the number of additional false occurrences it can tolerate. Occurrence indexes
update only affected rules; a queue processes rules with zero or negative slack.
An iterative trail, a priority heap, and saved phases avoid recursive search and
repeated full scans. No external solver is used.

The included 300x300 input completed in 18.2 and 18.5 seconds with a validated
zero penalty using Python 3.14 on the development machine. These are end-to-end
measurements, not a guarantee for other inputs or hardware. A zero penalty proves
optimality. For difficult puzzles, exact search can still take exponential time.
If a helper raises `RecursionError`, `solve_grid` reports it on stderr and returns
the best saved board, whose optimality may be unknown.

## Diagrams and checks

- [Overall flow](akari_solver_flow.svg) ([Mermaid source](akari_solver_flow.mmd))
- [Constraint search](akari_solver_constraints.svg) ([Mermaid source](akari_solver_constraints.mmd))

Run `python solver_checks.py` from the repository root for regression tests.
Run `python solver_checks.py --benchmark input_300x300.txt --timeout 60` to time
the CLI and independently validate its output. Validation runs after timing;
the 60-second timeout belongs to the benchmark, not `akari_solver.py`.

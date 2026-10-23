# Boolean_Satisfiability_Solvers
Akari Puzzle Solver


Run: python akari_simple.py < input.txt > output.txt

## Recursive KNF solver

The solver uses KNF constraints to represent the puzzle rules and recursive backtracking to search for a solution. The implementation uses functions, loops,
lists, dictionaries, and sets, with only `sys` and `itertools.combinations` from the
standard library.

Run in PowerShell:

```powershell
cmd /c "python akari_simple.py < input.txt > output_simple.txt"
```

`solve_grid` coordinates the search. `build_formula` turns the puzzle rules into
at-least-K constraints. `solve_constraints` initializes the search, and
`_search_assignments` recursively forces necessary assignments,
then tries True and False for the next unknown variable. The solver copies the
assignment list for each branch so that a failed branch leaves its parent's state
intact. Propagated assignments also record the decisions that caused them.
`learn_clause` negates the decision causes of a conflict to record a logically
implied clause, excluding unrelated decisions. Learned clauses are reused across
sibling branches and kept local to each formula and penalty-budget search.

The solver tries allowed clue-violation counts from smallest to largest, so the
first feasible count is optimal. It keeps the original input and output format:
dimensions and a grid in, then a penalty and grid with `L` bulbs out. Every white
cell must be lit, bulbs cannot see each other, and each wrong numbered clue adds
one penalty point.

The solver recomputes constraint counts during propagation and scans visibility
directly.
Search can take exponential time, and the visibility constraints can use
quadratic space. If Python's recursion limit is reached, the solver reports this
on stderr and returns its valid greedy board, whose clue penalty may be
suboptimal.

Run the standalone clause-learning tests with
`python -m unittest -v test_clause_learning.py`. These check clause reuse and
compare search results and every learned clause against exhaustive enumeration.

The legacy `test_akari_simple.py` suite also requires `akari_knf.py` and
`test_akari_knf.py`, which are not included in this checkout.

# Boolean_Satisfiability_Solvers
Akari Puzzle Solver


Run: python akari_knf.py < input.txt > output.txt

## Recursive KNF solver

The solver uses KNF constraints to represent the puzzle rules and recursive backtracking to search for a solution. The implementation uses functions, loops,
lists, and dictionaries, with only `sys` and `itertools.combinations` from the
standard library.

Run in PowerShell:

```powershell
cmd /c "python akari_simple.py < input.txt > output_simple.txt"
```

`solve_grid` coordinates the search. `build_formula` turns the puzzle rules into
at-least-K constraints. `find_model` repeatedly forces necessary assignments,
then tries True and False for the next unknown variable. The solver copies the
assignment list for each branch so that a failed branch leaves its parent's state
intact.

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

Run both test suites with `python -m unittest -v test_akari_knf.py test_akari_simple.py`.

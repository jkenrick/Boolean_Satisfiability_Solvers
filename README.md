# Akari Puzzle Solver

Solves Akari puzzles using KNF (at-least-K) constraints, unit propagation,
branching, backtracking, clause learning, and satisfiability checks.

Requires Python 3.9 or newer. No extra packages are needed.

Run in PowerShell:

```powershell
cmd /c "python akari_solver.py < input.txt > output.txt"
```

Input starts with the row and column counts, followed by the grid:
`.` for white cells, `X` for walls, and `0` through `4` for numbered clues.

Output contains the penalty score followed by the completed grid, with `L`
marking bulbs. Every white cell is lit, bulbs cannot see each other, and each
incorrect numbered clue adds one penalty point.

The solver searches for the lowest penalty. If the recursion limit is reached,
it returns a valid fallback board that may have a higher penalty.

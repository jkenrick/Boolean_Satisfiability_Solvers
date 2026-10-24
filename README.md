# Akari Puzzle Solver

`akari_solver.py` is a custom Python solver using KNF (at-least-K) constraints,
unit propagation, branching, backtracking, clause learning, and satisfiability
checks. Requires Python 3.9 or newer; no external solver or extra packages.

Run in PowerShell:

```powershell
cmd /c "python akari_solver.py < input.txt > output.txt"
```

Input starts with the row and column counts, followed by the grid:
`.` for white cells, `X` for walls, and `0` through `4` for numbered clues.

Output contains the penalty score followed by the completed grid, with `L`
marking bulbs. Every white cell is lit, bulbs cannot see each other, and each
incorrect numbered clue adds one penalty point.

The solver starts with a greedy board, tries a zero penalty, then uses a binary
budget search to find the lowest penalty. Each budget gets an independent search.
List storage is the default and the only supported `--storage` option.

Propagation updates only affected constraints. Search uses conflict priorities,
saved decision values, FirstUIP learning, and an iterative trail for backtracking.
The supplied 300x300 puzzle completed in **18.2 and 18.5 seconds**, both with a
validated zero penalty, using Python 3.14 on this machine. Other puzzles and
machines may take longer; exact search can take exponential time.

Check the custom solver with `python solver_checks.py`. Benchmark and independently
validate the 300x300 puzzle with a 60-second timeout:

```sh
python solver_checks.py --benchmark input_300x300.txt --timeout 60
```

The benchmark times the complete CLI and checks the output independently after
timing. Its timeout applies to the benchmark subprocess, not the solver itself.

See [solver details](docs/README.md), the [overall flow](docs/akari_solver_flow.svg),
and the [constraint search](docs/akari_solver_constraints.svg). Editable Mermaid
sources are included alongside the diagrams.

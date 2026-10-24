# Akari Puzzle Solver

Solves Akari puzzles using KNF (at-least-K) constraints, unit propagation,
occurrence-based branching, FirstUIP clause learning, and non-chronological
backtracking. Search uses an iterative assignment trail.

The custom solver requires Python 3.9 or newer and no extra packages.

Python list storage remains the default because it is faster on the measured
puzzles. Use `--storage compact` for packed integer storage, `--storage trie`
for shared prefixes, or `--storage zbdd` for zero-suppressed binary decision
diagrams that also share subgraphs. These alternatives preserve KNF thresholds
and repeated literals, remove exact duplicate constraints, and share immutable
blocks between independent budget searches.

The alternative backends trade runtime for memory savings or structural sharing.
Trie and ZBDD modes reconstruct clauses during propagation; building a ZBDD also
uses temporary trie memory. Use `--storage list` to select the default explicitly.

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
it returns the best valid board found so far, which may have a higher penalty.

The optional `akari_solver_z3.py` variant uses Z3 instead of the custom search.
It is a standalone file containing its own input validation, KNF encoding,
greedy bounds, zero-first binary budget search, and output formatting. These
follow the original solver, using plain list storage. Each budget starts a fresh
solver in both variants; the Z3 version translates KNF into Boolean/pseudo-Boolean
constraints. Its only external dependency is `z3-solver`; install the pinned
version into your Python environment:

```sh
python -m pip install -r requirements-z3.txt
```

If copying just the standalone file, install with `python -m pip install z3-solver`.

Run it using the same redirection as the original:

```powershell
cmd /c "python akari_solver_z3.py < input.txt > output_z3.txt"
```

Diagrams show the [overall function flow](docs/akari_solver_z3_flow.svg) and
[Z3 constraint solving](docs/akari_solver_z3_constraints.svg). Each SVG has an
editable Mermaid `.mmd` source alongside it.

Compare end-to-end runtimes with the same Python interpreter and inputs:

```sh
python benchmark_akari.py input.txt input2.txt input_40x40.txt --repeat 3 --timeout 30
```

The benchmark prints CSV with median seconds, scores, and completion status.
Times include interpreter startup, imports, encoding, search, and output.
Solution validation runs outside the timed interval. Timeouts and solver errors
are reported explicitly; different completed penalty scores cause a nonzero exit.
Pass `input_300x300.txt` to compare the large puzzle. Both solvers use list storage
in this comparison. Run the combined correctness checks with
`python -m unittest tests z3_tests` after installing Z3.

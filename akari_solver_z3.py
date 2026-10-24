"""Solve Akari with Z3 using the custom solver's encoding and budget search.

Install: python -m pip install -r requirements-z3.txt
Run: python akari_solver_z3.py < input.txt > output_z3.txt
"""

import argparse
import sys

try:
    import z3
except ImportError:
    z3 = None

from akari_solver import build_formula, count_violations, greedy_fallback, read_grid
from clause_storage import STORAGE_CHOICES


def require_z3():
    if z3 is None:
        raise RuntimeError("Z3 is required; install it with: "
                           "python -m pip install -r requirements-z3.txt")


def solve_constraints(constraints, assignment):
    """Solve the same at-least-k rules with a fresh Z3 Solver for each call."""
    require_z3()
    variables = [None] + [z3.Bool("v" + str(variable))
                          for variable in range(1, len(assignment))]
    # Cache both polarities instead of rebuilding a Not for every occurrence.
    negatives = [None] + [z3.Not(variable) for variable in variables[1:]]
    solver = z3.Solver()
    for literals, minimum in constraints:
        if minimum <= 0:
            continue
        if minimum > len(literals):
            return None
        terms = [variables[literal] if literal > 0 else negatives[-literal]
                 for literal in literals]
        if minimum == 1:
            solver.add(z3.Or(terms))
        elif minimum == len(literals):
            solver.add(*terms)
        else:
            # Repeated literals retain their occurrence counts, as in KNF.
            solver.add(z3.PbGe([(term, 1) for term in terms], minimum))
    for variable in range(1, len(assignment)):
        if assignment[variable] is not None:
            solver.add(variables[variable] == assignment[variable])

    status = solver.check()
    if status == z3.unsat:
        return None
    if status != z3.sat:
        # Unknown must not be mistaken for an impossible penalty budget.
        raise RuntimeError("Z3 returned unknown: " + solver.reason_unknown())
    model = solver.model()
    return [None] + [z3.is_true(model.eval(variable, model_completion=True))
                     for variable in variables[1:]]


def solve_grid(grid, diagnostics=None, storage="list"):
    """Use the same greedy bound, zero-first binary search, and output format."""
    require_z3()
    best_bulbs = greedy_fallback(grid)
    best_score = count_violations(grid, best_bulbs)
    if best_score > 0:
        cells, constraints, relaxations = build_formula(grid, storage)
        negative_relaxations = [-variable for variable in relaxations]
        lower_bound = 0
        budget = 0
        while lower_bound < best_score:
            limited = constraints + [(negative_relaxations, len(relaxations) - budget)]
            assignment = [None] * (len(cells) + len(relaxations) + 1)
            model = solve_constraints(limited, assignment)
            if model is None:
                lower_bound = budget + 1
            else:
                best_bulbs = [position for variable, position in enumerate(cells, 1)
                              if model[variable]]
                best_score = count_violations(grid, best_bulbs)
            budget = (lower_bound + best_score) // 2

    completed = [list(row) for row in grid]
    for row, column in best_bulbs:
        completed[row][column] = "L"
    return str(best_score) + "\n" + "".join("".join(row) + "\n" for row in completed)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Solve an Akari puzzle with Z3.")
    parser.add_argument("--storage", choices=("list",) + STORAGE_CHOICES, default="list",
                        help="input clause storage representation (default: list)")
    args = parser.parse_args(argv)
    try:
        require_z3()
        grid = read_grid(sys.stdin)
        output = solve_grid(grid, sys.stderr, args.storage)
    except ValueError as error:
        print("Invalid input: " + str(error), file=sys.stderr)
        return 2
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Solve Akari with Z3 using the custom solver's encoding and budget search.

Install: python -m pip install z3-solver
Run: python akari_solver_z3.py < input.txt > output_z3.txt
"""

import argparse
from itertools import combinations
import sys

# Keep --help available even when the optional solver package is not installed.
try:
    import z3
except ImportError:
    z3 = None


# Rows increase downward; these offsets move up, down, left, and right.
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def read_grid(stream):
    """Read and validate the dimensions and grid from an input stream."""
    dimensions = stream.readline().split()
    if len(dimensions) != 2:
        raise ValueError("expected two positive integer dimensions")
    # Reject signs and non-ASCII digits before converting the dimensions.
    for dimension in dimensions:
        if not dimension.isascii() or not dimension.isdigit():
            raise ValueError("dimensions must be positive integers")
    row_count, column_count = map(int, dimensions)
    if row_count < 1 or column_count < 1 or row_count * column_count > 100000:
        raise ValueError("dimensions must satisfy 1 <= rows*columns <= 100000")

    grid = []
    # Require a rectangular board with exactly the declared number of rows.
    for row_index in range(row_count):
        # Remove only the line ending, so accidental spaces are still rejected.
        row = stream.readline().removesuffix("\n").removesuffix("\r")
        if len(row) != column_count:
            raise ValueError("wrong length or missing row " + str(row_index + 1))
        # Only white cells, walls, and digits belong in the input; L is output.
        for cell in row:
            if cell not in ".X01234":
                raise ValueError("invalid grid character: " + cell)
        grid.append(row)
    # Allow trailing blank lines, but reject extra puzzle data.
    for line in stream:
        if line.strip():
            raise ValueError("unexpected data after grid")
    return grid


def visible_cells(grid, row, column):
    """Return a white cell and all white cells it can illuminate."""
    # A bulb lights its own square, even if walls block all four directions.
    visible = [(row, column)]
    for row_step, column_step in DIRECTIONS:
        next_row = row + row_step
        next_column = column + column_step
        # Stop the ray at the board's edge or the first gray cell.
        while 0 <= next_row < len(grid) and 0 <= next_column < len(grid[0]):
            # Both X and numbered cells block light.
            if grid[next_row][next_column] != ".":
                break
            visible.append((next_row, next_column))
            next_row += row_step
            next_column += column_step
    return visible


def build_formula(grid):
    """Encode lighting, bulb conflicts, and numbered clues as KNF constraints."""
    cells = []
    variable_at = {}
    # Assign one Boolean variable per white cell, in row order.
    for row in range(len(grid)):
        for column in range(len(grid[0])):
            if grid[row][column] == ".":
                cells.append((row, column))
                # IDs start at 1; ID n corresponds to cells[n - 1].
                variable_at[(row, column)] = len(cells)

    # Each entry is (literals, minimum); every constraint must be satisfied.
    constraints = []
    # Each white cell belongs to one horizontal and one vertical segment.
    # Keep references to those segments so illumination needs no repeated rays.
    row_segments = [None] * (len(cells) + 1)
    column_segments = [None] * (len(cells) + 1)
    for segment_at, row_step, column_step in (
        (row_segments, 0, 1), (column_segments, 1, 0)
    ):
        for row, column in cells:
            if segment_at[variable_at[(row, column)]] is not None:
                continue
            segment = []
            # Row order ensures this is the first white cell in the segment.
            while (row, column) in variable_at:
                variable = variable_at[(row, column)]
                segment.append(variable)
                segment_at[variable] = segment
                row += row_step
                column += column_step
            if len(segment) > 1:
                # At most one bulb: at least n-1 cells must have no bulb.
                constraints.append(([-variable for variable in segment],
                                    len(segment) - 1))

    for variable in range(1, len(cells) + 1):
        # The segments intersect at this cell; include its variable only once.
        visible_variables = row_segments[variable] + [
            other for other in column_segments[variable] if other != variable
        ]
        # At least one visible position, including this cell, must have a bulb.
        constraints.append((visible_variables, 1))

    relaxation_variables = []
    # Locate numbered cells and encode their required adjacent bulb counts.
    for row in range(len(grid)):
        for column in range(len(grid[0])):
            if grid[row][column] not in "01234":
                continue
            required = int(grid[row][column])
            neighbors = []
            # A clue counts immediate orthogonal neighbors, not whole sight lines.
            for row_step, column_step in DIRECTIONS:
                position = (row + row_step, column + column_step)
                # Only white cells have variables. This dictionary lookup also
                # excludes walls and positions outside the grid.
                if position in variable_at:
                    neighbors.append(variable_at[position])

            # Reserve a new variable after the bulb IDs; True permits this clue
            # to be violated, while False requires its exact count.
            relaxation = len(cells) + len(relaxation_variables) + 1
            relaxation_variables.append(relaxation)
            if required > len(neighbors):
                # An impossible clue must spend one violation from every budget.
                constraints.append(([relaxation], 1))
                continue

            # At most d bulbs: every group of d+1 neighbors needs a non-bulb.
            for group in combinations(neighbors, required + 1):
                # A True relaxation satisfies this clause and disables its rule.
                literals = [relaxation]
                for variable in group:
                    literals.append(-variable)
                # For a 1 clue, a pair a,b adds (relaxation OR NOT a OR NOT b).
                constraints.append((literals, 1))
            # At least d bulbs: no group of m-d+1 neighbors may be entirely off.
            # A group size greater than m produces no clauses, handling d = 0.
            for group in combinations(neighbors, len(neighbors) - required + 1):
                # Positive IDs require a bulb in the group unless the clue relaxes.
                constraints.append(([relaxation] + list(group), 1))
    return cells, constraints, relaxation_variables


def require_z3():
    """Report the external dependency with a standalone installation command."""
    if z3 is None:
        raise RuntimeError("Z3 is required; install it with: "
                           "python -m pip install z3-solver")


def solve_constraints(constraints, assignment):
    """Solve the same at-least-k rules with a fresh Z3 Solver for each call."""
    require_z3()
    # Match the formula's positive variable IDs; index zero stays unused.
    variables = [None] + [z3.Bool("v" + str(variable))
                          for variable in range(1, len(assignment))]
    # Cache both polarities instead of rebuilding a Not for every occurrence.
    negatives = [None] + [z3.Not(variable) for variable in variables[1:]]
    # Each call gets an isolated solver, so learned facts cannot cross budgets.
    solver = z3.Solver()
    for literals, minimum in constraints:
        # A nonpositive minimum is satisfied without assigning any literals.
        if minimum <= 0:
            continue
        # Even making every listed occurrence true cannot satisfy this rule.
        if minimum > len(literals):
            return None
        # Positive IDs require True; negative IDs require the corresponding Not.
        terms = [variables[literal] if literal > 0 else negatives[-literal]
                 for literal in literals]
        if minimum == 1:
            # An ordinary OR clause needs at least one true literal.
            solver.add(z3.Or(terms))
        elif minimum == len(literals):
            # When every occurrence is needed, assert each literal directly.
            solver.add(*terms)
        else:
            # Weight one per occurrence encodes the remaining KNF thresholds.
            # Repeated literals retain their occurrence counts, as in KNF.
            solver.add(z3.PbGe([(term, 1) for term in terms], minimum))
    # Treat caller-supplied assignments as assumptions for this solver only.
    for variable in range(1, len(assignment)):
        if assignment[variable] is not None:
            solver.add(variables[variable] == assignment[variable])

    # Z3 performs propagation, branching, backtracking, and learning internally.
    status = solver.check()
    if status == z3.unsat:
        return None
    if status != z3.sat:
        # Unknown must not be mistaken for an impossible penalty budget.
        raise RuntimeError("Z3 returned unknown: " + solver.reason_unknown())
    model = solver.model()
    # Complete unused variables with Boolean values while preserving index zero.
    return [None] + [z3.is_true(model.eval(variable, model_completion=True))
                     for variable in variables[1:]]


def greedy_fallback(grid):
    """Place nonconflicting bulbs until every white cell is illuminated."""
    # Store board positions so the fallback works independently of the formula.
    bulbs = []
    bulb_positions = set()
    for row in range(len(grid)):
        for column in range(len(grid[0])):
            if grid[row][column] == ".":
                already_lit = False
                # Any visible existing bulb means this cell needs no new one.
                for position in visible_cells(grid, row, column):
                    if position in bulb_positions:
                        already_lit = True
                        break
                # An unlit cell sees no existing bulb, so adding one is conflict-free.
                if not already_lit:
                    bulbs.append((row, column))
                    bulb_positions.add((row, column))
    # Skipped cells stay lit because bulbs are never removed; R1 is always zero.
    return bulbs


def count_violations(grid, bulbs):
    """Count numbered clues whose adjacent bulb count differs from their digit."""
    bulbs = set(bulbs)
    violations = 0
    for row in range(len(grid)):
        for column in range(len(grid[0])):
            if grid[row][column] in "01234":
                adjacent_bulbs = 0
                # Count immediate neighbors only; diagonal or distant bulbs do not count.
                for row_step, column_step in DIRECTIONS:
                    if (row + row_step, column + column_step) in bulbs:
                        adjacent_bulbs += 1
                # One wrong clue costs one point, regardless of the difference.
                if adjacent_bulbs != int(grid[row][column]):
                    # Use the actual mismatch: a True relaxation only permits one.
                    violations += 1
    return violations


def solve_grid(grid, diagnostics=None):
    """Find the minimum clue penalty and format the score and completed grid."""
    require_z3()
    # Establish a fully lit, nonconflicting answer before starting the exact search.
    best_bulbs = greedy_fallback(grid)
    best_score = count_violations(grid, best_bulbs)
    # A zero penalty is already optimal, so no search is needed.
    if best_score > 0:
        cells, constraints, relaxations = build_formula(grid)
        # A negated relaxation is true when its clue must be enforced.
        negative_relaxations = []
        for variable in relaxations:
            negative_relaxations.append(-variable)
        # First try zero; then binary-search between the smallest possible
        # penalty and the best feasible score. Each failed budget raises the
        # lower bound; each model can improve the saved board and upper bound.
        lower_bound = 0
        budget = 0
        while lower_bound < best_score:
            # With m clues and budget b, at least m-b must be enforced.
            # Add this budget without changing the base puzzle constraints.
            limited = constraints + [(negative_relaxations, len(relaxations) - budget)]
            # Start each budget with fresh unknowns for bulbs and relaxations.
            assignment = [None] * (len(cells) + len(relaxations) + 1)
            # Exact search may take exponential time on difficult boards.
            model = solve_constraints(limited, assignment)
            if model is not None:
                best_bulbs = []
                # Extract only bulb variables; the remaining IDs relax clues.
                for index, position in enumerate(cells):
                    if model[index + 1]:
                        best_bulbs.append(position)
                # Score the actual board, since permitted violations may be unused.
                best_score = count_violations(grid, best_bulbs)
            else:
                lower_bound = budget + 1
            budget = (lower_bound + best_score) // 2
        # Matching bounds prove the saved board has the minimum penalty.

    completed = []
    # Copy rows into mutable lists while leaving the input puzzle unchanged.
    for row in grid:
        completed.append(list(row))
    # Overlay bulbs at white-cell positions, preserving every wall and digit.
    for row, column in best_bulbs:
        completed[row][column] = "L"
    # R1 is zero by construction, so the total penalty is the violated clue count R2.
    output = str(best_score) + "\n"
    for row in completed:
        output += "".join(row) + "\n"
    return output


def main(argv=None):
    """Read a puzzle from stdin and write the solution, or report invalid input."""
    parser = argparse.ArgumentParser(description="Solve an Akari puzzle with Z3.")
    parser.parse_args(argv)
    try:
        require_z3()
        # Parse the full input before solving or writing any board output.
        grid = read_grid(sys.stdin)
        output = solve_grid(grid, sys.stderr)
    except ValueError as error:
        # Reject invalid input before writing any partial board to stdout.
        print("Invalid input: " + str(error), file=sys.stderr)
        return 2
    except RuntimeError as error:
        # Report missing dependencies or unknown results without a partial board.
        print(str(error), file=sys.stderr)
        return 1
    # Write only the score and completed grid, allowing redirection to a file.
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

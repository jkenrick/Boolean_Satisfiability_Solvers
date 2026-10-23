"""Solve Akari using KNF constraints and recursive backtracking.

Run: python akari_simple.py < input.txt > output.txt
"""

from itertools import combinations
import sys


# Rows increase downward; these offsets move up, down, left, and right.
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def read_grid(stream):
    """Read and validate the dimensions and grid from an input stream."""
    # Check the dimensions before using them as loop bounds or grid sizes.
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
    # Read exactly the declared number of rows so the board is rectangular.
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
    # Trace each direction separately so light follows straight lines.
    for row_step, column_step in DIRECTIONS:
        next_row = row + row_step
        next_column = column + column_step
        # Stop the ray at the board's edge or the first gray cell.
        while 0 <= next_row < len(grid) and 0 <= next_column < len(grid[0]):
            # Both X and numbered cells block light.
            if grid[next_row][next_column] != ".":
                break
            visible.append((next_row, next_column))
            # Advance one square along the same ray.
            next_row += row_step
            next_column += column_step
    return visible


def build_formula(grid):
    """Encode lighting, bulb conflicts, and numbered clues as KNF constraints."""
    cells = []
    variable_at = {}
    # Assign one Boolean variable per white cell, in row order.
    for row in range(len(grid)):
        # Gray cells have no bulb variable because bulbs cannot be placed there.
        for column in range(len(grid[0])):
            if grid[row][column] == ".":
                cells.append((row, column))
                # IDs start at 1; ID n corresponds to cells[n - 1].
                variable_at[(row, column)] = len(cells)

    # Each entry is (literals, minimum); every constraint must be satisfied.
    constraints = []
    # Encode illumination and bulb conflicts for every white cell.
    for row, column in cells:
        variable = variable_at[(row, column)]
        visible_variables = []
        # Convert visible positions into IDs used by the Boolean constraints.
        for position in visible_cells(grid, row, column):
            other = variable_at[position]
            visible_variables.append(other)
            # Process each visible pair once, excluding a cell paired with itself.
            if variable < other:
                # NOT x OR NOT y: at least one of the two cells has no bulb.
                constraints.append(([-variable, -other], 1))
        # At least one visible position, including this cell, must have a bulb.
        constraints.append((visible_variables, 1))

    relaxation_variables = []
    # Locate numbered cells and encode their required adjacent bulb counts.
    for row in range(len(grid)):
        # Skip unnumbered cells because they do not impose a clue count.
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
                # Negate each bulb ID so the clause requires one bulb to be off.
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


def find_model(constraints, assignment):
    """Propagate forced values, then recursively try both values of a variable."""
    # Assignment entries are None (unknown), True (on), or False (off).
    changed = True
    # Repeat propagation until a full pass makes no changes: a fixed point.
    while changed:
        changed = False
        # Recount each rule from its current assignments instead of caching counts.
        for literals, minimum in constraints:
            true_count = 0
            unknown_literals = []
            # Count listed occurrences; repeated literals each count separately.
            for literal in literals:
                # abs selects the variable; the sign selects its required value.
                value = assignment[abs(literal)]
                if value is None:
                    # Unknown is distinct from False: either value is still possible.
                    unknown_literals.append(literal)
                elif value == (literal > 0):
                    # For example, literal -3 is true when variable 3 is False.
                    true_count += 1

            if true_count >= minimum:
                # Already true literals are enough; nothing else must be forced.
                continue
            # True plus unknown occurrences bounds the maximum still achievable.
            possible_count = true_count + len(unknown_literals)
            if possible_count < minimum:
                # Even making every unknown literal true cannot rescue this rule.
                return None
            if possible_count == minimum:
                # With exactly enough possible literals, every unknown is needed.
                for literal in unknown_literals:
                    variable = abs(literal)
                    needed_value = literal > 0
                    if assignment[variable] is None:
                        # Record the forced value, then revisit earlier rules too.
                        assignment[variable] = needed_value
                        changed = True
                    elif assignment[variable] != needed_value:
                        # Another occurrence in this pass forced the opposite
                        # value, so the branch contains contradictory demands.
                        return None

    # Decide on the first unknown variable; index 0 is unused because IDs start at 1.
    for variable in range(1, len(assignment)):
        if assignment[variable] is None:
            # Try both values so a failed preference cannot exclude a solution.
            for value in (True, False):
                # Preserve the parent's propagated state in a separate list.
                branch = assignment.copy()
                # Make one decision before propagating its consequences recursively.
                branch[variable] = value
                model = find_model(constraints, branch)
                if model is not None:
                    return model
                # Discarding this child restores the parent automatically;
                # no shared trail or counters need to be undone.
            # Both values failed, so no completion of this parent can succeed.
            return None
    # No unknowns or conflicts remain, so the complete assignment satisfies all rules.
    return assignment


def greedy_fallback(grid):
    """Place nonconflicting bulbs until every white cell is illuminated."""
    # Store board positions so the fallback works independently of the formula.
    bulbs = []
    # Consider possible bulb locations in a fixed row order.
    for row in range(len(grid)):
        # Only white cells can receive bulbs.
        for column in range(len(grid[0])):
            if grid[row][column] == ".":
                already_lit = False
                # Any visible existing bulb means this cell needs no new one.
                for position in visible_cells(grid, row, column):
                    if position in bulbs:
                        already_lit = True
                        break
                # An unlit cell sees no existing bulb, so adding one is conflict-free.
                if not already_lit:
                    bulbs.append((row, column))
    # Skipped cells stay lit because bulbs are never removed; R1 is always zero.
    return bulbs


def count_violations(grid, bulbs):
    """Count numbered clues whose adjacent bulb count differs from their digit."""
    violations = 0
    # Check every numbered cell against the final bulb positions.
    for row in range(len(grid)):
        # Unnumbered cells do not contribute to the clue penalty R2.
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
    # Establish a fully lit, nonconflicting answer before starting the exact search.
    best_bulbs = greedy_fallback(grid)
    best_score = count_violations(grid, best_bulbs)
    # A zero penalty is already optimal, so no search is needed.
    if best_score > 0:
        cells, constraints, relaxations = build_formula(grid)
        try:
            # Try budgets in increasing order. The greedy score is already
            # feasible, so the first smaller feasible budget proves optimality.
            for budget in range(best_score):
                negative_relaxations = []
                # A negated relaxation is true when its clue must be enforced.
                for variable in relaxations:
                    negative_relaxations.append(-variable)
                # With m clues and budget b, at least m-b must be enforced.
                # Add this budget without changing the base puzzle constraints.
                limited = constraints + [(negative_relaxations, len(relaxations) - budget)]
                # Start each budget with fresh unknowns for bulbs and relaxations.
                assignment = [None] * (len(cells) + len(relaxations) + 1)
                # Recursive search may take exponential time on difficult boards.
                model = find_model(limited, assignment)
                if model is not None:
                    best_bulbs = []
                    # Extract only bulb variables; the remaining IDs relax clues.
                    for index, position in enumerate(cells):
                        if model[index + 1]:
                            best_bulbs.append(position)
                    # Score the actual board, since permitted violations may be unused.
                    best_score = count_violations(grid, best_bulbs)
                    break
                # An impossible budget leads to the next, less restrictive one.
            # If every smaller budget fails, the greedy board is itself optimal.
        except RecursionError:
            # Too many nested decisions can exceed Python's call-stack limit.
            # The greedy board is still valid, but optimality is then unknown.
            if diagnostics is not None:
                print("Recursion limit reached; using the greedy board.", file=diagnostics)

    completed = []
    # Copy rows into mutable lists while leaving the input puzzle unchanged.
    for row in grid:
        completed.append(list(row))
    # Overlay bulbs at white-cell positions, preserving every wall and digit.
    for row, column in best_bulbs:
        completed[row][column] = "L"
    # R1 is zero by construction, so the total penalty is the violated clue count R2.
    output = str(best_score) + "\n"
    # Convert each modified row back to a string in the required output format.
    for row in completed:
        output += "".join(row) + "\n"
    return output


def main():
    """Read a puzzle from stdin and write the solution, or report invalid input."""
    try:
        # Pass stderr separately so search diagnostics never enter the board output.
        grid = read_grid(sys.stdin)
        output = solve_grid(grid, sys.stderr)
    except ValueError as error:
        # Reject invalid input before writing any partial board to stdout.
        print("Invalid input: " + str(error), file=sys.stderr)
        return 2
    # Write only the score and completed grid, allowing redirection to a file.
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

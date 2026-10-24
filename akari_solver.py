"""Solve Akari

Run: python akari_solver.py < input.txt > output.txt
"""

import argparse
from collections import deque
from heapq import heapify, heappop, heappush
from itertools import combinations
import sys


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


def build_formula(grid, storage="list"):
    """Encode lighting, bulb conflicts, and numbered clues as KNF constraints."""
    if storage != "list":
        raise ValueError("only list storage is supported by this standalone solver")
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


def solve_constraints(constraints, assignment):
    """Initialize an isolated search and return a satisfying assignment, if any."""
    return ConstraintSearch(constraints, assignment).solve()


class ConstraintSearch:
    """Iterative KNF search with FirstUIP learning and non-chronological backtracking."""

    def __init__(self, constraints, assignment):
        # Learned clauses and assignments stay local to this budget search.
        self.constraints = []
        self.assignment = [None] * len(assignment)
        self.levels = [0] * len(assignment)
        self.reasons = [None] * len(assignment)
        self.decision_level = 0
        self.trail = []
        # Slack is the number of additional false occurrences a rule allows.
        # Only constraints containing a newly false literal need to be updated.
        self.slack = []
        self.positive_occurrences = [[] for _ in assignment]
        self.negative_occurrences = [[] for _ in assignment]
        self.pending = deque()
        self.queued = []
        self.learned_clauses = set()
        # Bulbs are sparse: start with no bulb, then save successful implications
        # and decision values for reuse after backtracking.
        self.phases = [False] * len(assignment)
        occurrences = [0] * len(assignment)
        for literals, minimum in constraints:
            self.add_constraint(literals, minimum)
            for literal in literals:
                occurrences[abs(literal)] += 1
        # Caller-supplied values are fixed assumptions at level zero. Keep them
        # in explanations: they need not be consequences of the formula itself.
        for variable in range(1, len(assignment)):
            if assignment[variable] is not None:
                self.assign(variable if assignment[variable] else -variable, None)
        # Start with occurrence priorities, then favor variables in recent
        # conflicts. This avoids repeatedly undoing thousands of unrelated choices.
        scale = max(occurrences, default=1) or 1
        self.activity = [count / scale for count in occurrences]
        self.activity_increment = 1.0
        self.branch_heap = [(-self.activity[v], v) for v in range(1, len(assignment))]
        heapify(self.branch_heap)

    def add_constraint(self, literals, minimum):
        """Index a rule and schedule it if its current slack permits no more falsity."""
        index = len(self.constraints)
        self.constraints.append((literals, minimum))
        slack = len(literals) - minimum
        for literal in literals:
            variable = abs(literal)
            occurrences = (self.positive_occurrences if literal > 0
                           else self.negative_occurrences)
            occurrences[variable].append(index)
            value = self.assignment[variable]
            if value is not None and value != (literal > 0):
                slack -= 1
        self.slack.append(slack)
        self.queued.append(slack <= 0)
        if slack <= 0:
            self.pending.append(index)

    def assign(self, literal, reason):
        """Append a decision or implication to the assignment trail."""
        variable = abs(literal)
        self.assignment[variable] = literal > 0
        self.levels[variable] = self.decision_level
        # An implication's reason contains the other, currently false literals
        # of its explaining clause. None marks a decision, not an implication.
        self.reasons[variable] = reason
        self.phases[variable] = literal > 0
        self.trail.append(literal)
        occurrences = (self.negative_occurrences if literal > 0
                       else self.positive_occurrences)
        for index in occurrences[variable]:
            self.slack[index] -= 1
            if self.slack[index] <= 0 and not self.queued[index]:
                self.queued[index] = True
                self.pending.append(index)

    def propagate(self):
        """Reach a propagation fixpoint, or return a false explaining clause."""
        assignment = self.assignment
        # === 1) Unit propagation: process only rules whose slack reaches zero ===
        while self.pending:
            index = self.pending.popleft()
            self.queued[index] = False
            literals, minimum = self.constraints[index]
            unknown_literals = []
            false_literals = []
            for literal in literals:
                value = assignment[abs(literal)]
                if value is None:
                    unknown_literals.append(literal)
                elif value != (literal > 0):
                    false_literals.append(literal)

            # === 5) Satisfiability check: too many false occurrences ===
            if self.slack[index] < 0:
                # Any n-k+1 occurrences of an at-least-k rule form an implied
                # OR clause, including repeated occurrences and opposite signs.
                needed = max(0, len(literals) - minimum + 1)
                return frozenset(false_literals[:needed])

            # All remaining occurrences must be true. This fixed set of false
            # literals explains each implication without expanding KNF to CNF.
            reason = frozenset(false_literals)
            for literal in unknown_literals:
                variable = abs(literal)
                if assignment[variable] is None:
                    self.assign(literal, reason)
                elif assignment[variable] != (literal > 0):
                    return reason | {literal}
        return None

    def analyze_conflict(self, conflict):
        """Resolve backwards to the first clause with one current-level literal."""
        clause = set(conflict)
        current_level = max(self.levels[abs(literal)] for literal in clause)
        pending = sum(self.levels[abs(literal)] == current_level for literal in clause)
        index = len(self.trail) - 1
        while pending > 1:
            literal = -self.trail[index]
            index -= 1
            if literal not in clause or self.levels[abs(literal)] != current_level:
                continue
            # Resolve away the most recently implied variable. Its reason
            # mentions only assignments earlier on the trail.
            clause.remove(literal)
            pending -= 1
            for cause in self.reasons[abs(literal)]:
                if cause not in clause:
                    clause.add(cause)
                    pending += self.levels[abs(cause)] == current_level

        asserting = next(literal for literal in clause
                         if self.levels[abs(literal)] == current_level)
        others = sorted(clause - {asserting})
        backjump_level = max((self.levels[abs(literal)] for literal in others), default=0)
        return [asserting] + others, backjump_level

    def learn_clause(self, literals):
        """Index a logically implied clause once, for reuse after backtracking."""
        # === 4) Clause learning ===
        key = tuple(sorted(set(literals)))
        if key not in self.learned_clauses:
            self.learned_clauses.add(key)
            self.add_constraint(list(key), 1)

    def prioritize_conflict(self, literals):
        """Raise recent conflict priorities and gradually decay older activity."""
        for variable in {abs(literal) for literal in literals}:
            self.activity[variable] += self.activity_increment
        self.activity_increment /= 0.95
        if self.activity_increment > 1e100:
            self.activity = [value * 1e-100 for value in self.activity]
            self.activity_increment *= 1e-100
            self.branch_heap = [(-self.activity[v], v)
                                for v in range(1, len(self.assignment))
                                if self.assignment[v] is None]
            heapify(self.branch_heap)

    def backtrack(self, level):
        """Undo all trail entries above the asserting level in one backjump."""
        # === 3) Backtracking: restore assignments and cached constraint slack ===
        while self.pending:
            self.queued[self.pending.popleft()] = False
        while self.trail and self.levels[abs(self.trail[-1])] > level:
            literal = self.trail.pop()
            variable = abs(literal)
            occurrences = (self.negative_occurrences if literal > 0
                           else self.positive_occurrences)
            for index in occurrences[variable]:
                self.slack[index] += 1
            self.assignment[variable] = None
            self.levels[variable] = 0
            self.reasons[variable] = None
            heappush(self.branch_heap, (-self.activity[variable], variable))
        self.decision_level = level

    def solve(self):
        """Propagate, learn and backjump, or decide by recent conflict activity."""
        while True:
            conflict = self.propagate()
            if conflict is not None:
                if not conflict or all(self.levels[abs(literal)] == 0 for literal in conflict):
                    return None
                learned, level = self.analyze_conflict(conflict)
                self.prioritize_conflict(set(conflict) | set(learned))
                self.learn_clause(learned)
                self.backtrack(level)
                # The learned clause is now unit: all other literals stayed
                # false, and its unique highest-level variable was unassigned.
                self.assign(learned[0], frozenset(learned[1:]))
                continue

            # === 2) Branching: choose an unassigned variable by conflict activity ===
            while self.branch_heap:
                priority, variable = heappop(self.branch_heap)
                if self.assignment[variable] is None and priority == -self.activity[variable]:
                    break
            else:
                # === 5) Satisfiability check: no unknown variables remain ===
                return self.assignment
            self.decision_level += 1
            # Reuse the last value after a backjump rather than restarting it.
            self.assign(variable if self.phases[variable] else -variable, None)


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


def solve_grid(grid, diagnostics=None, storage="list"):
    """Find the minimum clue penalty and format the score and completed grid."""
    # Establish a fully lit, nonconflicting answer before starting the exact search.
    best_bulbs = greedy_fallback(grid)
    best_score = count_violations(grid, best_bulbs)
    # A zero penalty is already optimal, so no search is needed.
    if best_score > 0:
        cells, constraints, relaxations = build_formula(grid, storage)
        # A negated relaxation is true when its clue must be enforced.
        negative_relaxations = []
        for variable in relaxations:
            negative_relaxations.append(-variable)
        try:
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
        except RecursionError:
            # Preserve the best board if a helper reaches the recursion limit.
            if diagnostics is not None:
                print("Recursion limit reached; using the best board found.", file=diagnostics)

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
    parser = argparse.ArgumentParser(description="Solve an Akari puzzle from standard input.")
    parser.add_argument("--storage", choices=("list",), default="list",
                        help="clause storage representation (default: list)")
    args = parser.parse_args(argv)
    try:
        # Pass stderr separately so search diagnostics never enter the board output.
        grid = read_grid(sys.stdin)
        output = solve_grid(grid, sys.stderr, args.storage)
    except ValueError as error:
        # Reject invalid input before writing any partial board to stdout.
        print("Invalid input: " + str(error), file=sys.stderr)
        return 2
    # Write only the score and completed grid, allowing redirection to a file.
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

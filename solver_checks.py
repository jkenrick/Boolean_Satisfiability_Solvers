"""Regression checks and an end-to-end benchmark for the custom Akari solver."""

import argparse
from copy import deepcopy
from itertools import product
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter
import unittest

import akari_solver as solver


def satisfies(constraints, model):
    return all(sum(model[abs(literal)] == (literal > 0) for literal in literals)
               >= minimum for literals, minimum in constraints)


def board_score(grid, bulbs):
    """Independently check bulb conflicts, illumination, and the clue penalty."""
    bulbs = set(bulbs)
    white = {(r, c) for r, row in enumerate(grid)
             for c, cell in enumerate(row) if cell == '.'}
    if not bulbs <= white:
        raise AssertionError('bulb placed on a wall or clue')
    illuminated = set(bulbs)
    steps = ((-1, 0), (1, 0), (0, -1), (0, 1))
    for row, column in bulbs:
        for dr, dc in steps:
            r, c = row + dr, column + dc
            while (r, c) in white:
                if (r, c) in bulbs:
                    raise AssertionError('two bulbs see each other')
                illuminated.add((r, c))
                r, c = r + dr, c + dc
    if illuminated != white:
        raise AssertionError('an unlit white cell remains')
    return sum(sum((r + dr, c + dc) in bulbs for dr, dc in steps) != int(cell)
               for r, row in enumerate(grid) for c, cell in enumerate(row)
               if cell in '01234')


def validate_output(grid, output):
    lines = output.splitlines()
    assert len(lines) == len(grid) + 1, 'incorrect number of output rows'
    bulbs = set()
    for r, (original, completed) in enumerate(zip(grid, lines[1:])):
        assert len(completed) == len(original), 'incorrect output row width'
        for c, (before, after) in enumerate(zip(original, completed)):
            assert after in '.L' if before == '.' else after == before, 'invalid cell'
            if after == 'L':
                bulbs.add((r, c))
    score = board_score(grid, bulbs)
    assert int(lines[0]) == score, 'reported score differs from the board penalty'
    return score


class SolverTests(unittest.TestCase):
    def test_random_knf_models_and_learned_clause_entailment(self):
        rng = random.Random(47319)
        for case in range(1500):
            n = rng.randint(1, 6)
            constraints = []
            for _ in range(rng.randint(0, 12)):
                literals = [rng.choice((-1, 1)) * rng.randint(1, n)
                            for _ in range(rng.randint(0, 7))]
                constraints.append((literals, rng.randint(-1, len(literals) + 1)))
            assumptions = [None] + [rng.choice((None, None, True, False)) for _ in range(n)]
            original = deepcopy(constraints)
            models = [[None] + list(v) for v in product((False, True), repeat=n)
                      if satisfies(constraints, [None] + list(v))]
            expected = [m for m in models
                        if all(v is None or m[i] == v
                               for i, v in enumerate(assumptions[1:], 1))]
            with self.subTest(case=case):
                search = solver.ConstraintSearch(constraints, assumptions)
                result = search.solve()
                self.assertEqual(result is not None, bool(expected))
                if result is not None:
                    self.assertIn(result, expected)
                learned = search.constraints[len(constraints):]
                for model in models:
                    self.assertTrue(satisfies(learned, model))
                self.assertEqual(constraints, original)

    def test_satisfiable_formulas_keep_every_original_model(self):
        rng = random.Random(38129)
        learned_count = 0
        for case in range(400):
            planted = [None] + [rng.choice((False, True)) for _ in range(6)]
            constraints = []
            for _ in range(15):
                literals = [rng.choice((-1, 1)) * rng.randint(1, 6)
                            for _ in range(rng.randint(2, 4))]
                if not any(planted[abs(lit)] == (lit > 0) for lit in literals):
                    literals[0] = -literals[0]
                true_count = sum(planted[abs(lit)] == (lit > 0) for lit in literals)
                constraints.append((literals, rng.randint(1, true_count)))
            with self.subTest(case=case):
                search = solver.ConstraintSearch(constraints, [None] * 7)
                model = search.solve()
                self.assertIsNotNone(model)
                self.assertTrue(satisfies(constraints, model))
                learned = search.constraints[len(constraints):]
                learned_count += len(learned)
                for values in product((False, True), repeat=6):
                    candidate = [None] + list(values)
                    if satisfies(constraints, candidate):
                        self.assertTrue(satisfies(learned, candidate))
        self.assertGreater(learned_count, 10)

    def test_backtrack_restores_slack_and_branch_candidates(self):
        constraints = [([-1, 2, 2], 2), ([-2, 3], 1), ([-3, -1], 1)]
        search = solver.ConstraintSearch(constraints, [None] * 4)
        search.decision_level = 1
        search.assign(1, None)
        self.assertIsNotNone(search.propagate())
        search.backtrack(0)
        self.assertEqual(search.assignment, [None] * 4)
        self.assertEqual(search.slack, [len(ls) - k for ls, k in constraints])
        model = search.solve()
        self.assertIsNotNone(model)
        self.assertTrue(satisfies(constraints, model))

    def test_learning_stays_within_its_formula_and_assumptions(self):
        constraints = [([-1, 2], 1), ([-1, -2], 1)]
        search = solver.ConstraintSearch(constraints, [None, True, None])
        self.assertIsNone(search.solve())
        self.assertIsNotNone(solver.solve_constraints(constraints, [None] * 3))
        strict = [([1], 1), ([-1], 1)]
        self.assertIsNone(solver.solve_constraints(strict, [None] * 2))
        self.assertEqual(strict, [([1], 1), ([-1], 1)])
        self.assertIsNotNone(solver.solve_constraints([([1], 1), ([-1], 0)], [None] * 2))

    def test_grid_optima_against_independent_enumeration(self):
        rng = random.Random(21784)
        grids = [['0.'], ['0.0'], ['0.1'], ['0..'], ['X.X', '.4.', 'X.X']]
        for _ in range(100):
            height, width = rng.randint(1, 3), rng.randint(1, 3)
            grids.append([''.join(rng.choice('......X01234') for _ in range(width))
                          for _ in range(height)])
        for grid in grids:
            with self.subTest(grid=grid):
                cells = [(r, c) for r, row in enumerate(grid)
                         for c, cell in enumerate(row) if cell == '.']
                optimum = len(''.join(grid))
                for values in product((False, True), repeat=len(cells)):
                    bulbs = [cell for cell, value in zip(cells, values) if value]
                    try:
                        optimum = min(optimum, board_score(grid, bulbs))
                    except AssertionError:
                        pass
                self.assertEqual(validate_output(grid, solver.solve_grid(grid)), optimum)

    def test_command_line(self):
        script = str(Path(solver.__file__).resolve())
        result = subprocess.run([sys.executable, '-B', script], input='1 3\n0.0\n',
                                text=True, capture_output=True, check=True, timeout=10)
        self.assertEqual(validate_output(['0.0'], result.stdout), 2)
        self.assertEqual(result.stderr, '')


def benchmark(paths, timeout):
    """Time the complete CLI; validate its solution outside the timed interval."""
    script = str(Path(solver.__file__).resolve())
    print('input,seconds,score,status', flush=True)
    for path in paths:
        puzzle = Path(path).read_text()
        with Path(path).open() as source:
            grid = solver.read_grid(source)
        start = perf_counter()
        try:
            result = subprocess.run([sys.executable, '-B', script], input=puzzle,
                                    text=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f'{path},{perf_counter() - start:.3f},,TIMEOUT', flush=True)
            return 1
        elapsed = perf_counter() - start
        if result.returncode:
            raise RuntimeError(result.stderr)
        score = validate_output(grid, result.stdout)
        print(f'{path},{elapsed:.3f},{score},valid', flush=True)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', nargs='+', metavar='INPUT')
    parser.add_argument('--timeout', type=float, default=60)
    args, remaining = parser.parse_known_args()
    if args.benchmark:
        parser.parse_args()
        sys.exit(benchmark(args.benchmark, args.timeout))
    unittest.main(argv=[sys.argv[0]] + remaining)

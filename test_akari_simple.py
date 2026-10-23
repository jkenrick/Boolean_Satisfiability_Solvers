"""Check the recursive KNF solver against exhaustive search and independent scoring."""

from io import StringIO
from itertools import product
from pathlib import Path
import random
import subprocess
import sys
import unittest
from unittest.mock import patch

import akari_simple
from akari_knf import score_board
from test_akari_knf import SAMPLE, brute_optimum


class SimpleSolverTests(unittest.TestCase):
    """Verify the simpler solver's search, output, and recursion-limit fallback."""

    def assert_solution(self, grid, expected_score):
        """Validate lighting, conflicts, unchanged gray cells, and the exact score."""
        output = akari_simple.solve_grid(grid)
        lines = output.splitlines()
        self.assertEqual(len(lines), len(grid) + 1)
        score = score_board(grid, tuple(lines[1:]))
        self.assertTrue(score.illuminated)
        self.assertEqual(score.r1, 0)
        self.assertEqual(score.r2, expected_score)
        self.assertEqual(int(lines[0]), score.total)
        self.assertTrue(output.endswith("\n"))

    def test_known_boards(self):
        """Cover empty, narrow, walled, feasible, and inconsistent clue layouts."""
        cases = [
            ((".",), 0),
            (("." * 50,), 0),
            ((".",) * 50, 0),
            (("X",), 0),
            (("X01234", "XXXXXX"), 4),
            (("0.",), 1),
            (("0..",), 0),
            (("4.", ".."), 1),
            (("X.X", ".4.", "X.X"), 0),
            (("0.1",), 1),
            (("0.0",), 2),
            (SAMPLE, 1),
        ]
        for grid, expected in cases:
            with self.subTest(grid=grid):
                self.assert_solution(grid, expected)

    def test_random_boards_against_exhaustive_search(self):
        """Match independently enumerated optima on small random puzzles."""
        generator = random.Random(21784)
        for case in range(150):
            row_count = generator.randint(1, 3)
            column_count = generator.randint(1, 4)
            grid = []
            for row_index in range(row_count):
                row = ""
                for column_index in range(column_count):
                    row += generator.choice("......X01234")
                grid.append(row)
            with self.subTest(case=case, grid=grid):
                self.assert_solution(tuple(grid), brute_optimum(tuple(grid)))

    def test_knf_search_against_exhaustive_search(self):
        """Check signed literals, repeated occurrences, forcing, and conflicts."""
        generator = random.Random(47319)
        for case in range(250):
            variable_count = generator.randint(1, 5)
            constraints = []
            for constraint_index in range(generator.randint(0, 8)):
                literals = []
                for occurrence in range(generator.randint(0, 6)):
                    literals.append(generator.choice([-1, 1]) *
                                    generator.randint(1, variable_count))
                minimum = generator.randint(-1, len(literals) + 1)
                constraints.append((literals, minimum))

            # Enumerate truth assignments directly rather than using the old
            # solver's search, so the expected satisfiability is independent.
            expected_satisfiable = False
            for values in product([False, True], repeat=variable_count):
                model = [None] + list(values)
                satisfied = True
                for literals, minimum in constraints:
                    true_count = 0
                    for literal in literals:
                        if model[abs(literal)] == (literal > 0):
                            true_count += 1
                    if true_count < minimum:
                        satisfied = False
                        break
                if satisfied:
                    expected_satisfiable = True
                    break

            with self.subTest(case=case):
                model = akari_simple.find_model(
                    constraints, [None] * (variable_count + 1)
                )
                self.assertEqual(model is not None, expected_satisfiable)
                if model is not None:
                    for literals, minimum in constraints:
                        true_count = sum(model[abs(literal)] == (literal > 0)
                                         for literal in literals)
                        self.assertGreaterEqual(true_count, minimum)

    def test_failed_branch_preserves_parent_assignment(self):
        """Undo a failed True decision by discarding its copied assignment."""
        constraints = [([-1, 2], 1), ([-1, -2], 1)]
        parent = [None, None, None]
        model = akari_simple.find_model(constraints, parent)
        self.assertFalse(model[1])
        self.assertEqual(parent, [None, None, None])

    def test_recursion_limit_retains_valid_fallback(self):
        """Return the greedy board and a diagnostic if recursion is exhausted."""
        diagnostics = StringIO()
        with patch.object(akari_simple, "find_model", side_effect=RecursionError):
            output = akari_simple.solve_grid(SAMPLE, diagnostics)
        score = score_board(SAMPLE, tuple(output.splitlines()[1:]))
        self.assertTrue(score.illuminated)
        self.assertEqual(score.r1, 0)
        self.assertEqual(int(output.splitlines()[0]), score.total)
        self.assertIn("Recursion limit", diagnostics.getvalue())

    def test_input_validation(self):
        """Accept supported line endings and reject malformed grids."""
        bad_inputs = [
            "", "1\n.\n", "1 2 3\n..\n", "-1 2\n", "0 1\n", "1 0\n",
            "1 100001\n", "1.0 2\n..\n", "1_0 1\n", "1 2\n.\n", "2 1\n.\n",
            "1 1\nL\n", "1 1\n5\n", "1 1\nA\n", "1 1\n \n", "1 1\n. \n",
            "1 1\n.\r\r\n", "1 1\n.\nX\n",
        ]
        for text in bad_inputs:
            with self.subTest(text=text), self.assertRaises(ValueError):
                akari_simple.read_grid(StringIO(text))
        self.assertEqual(akari_simple.read_grid(StringIO("1 2\r\n.X\r\n\n")), [".X"])
        self.assertEqual(akari_simple.read_grid(StringIO("1 1\n.")), ["."])

    def test_command_line(self):
        """Check a real subprocess for both a solved sample and invalid input."""
        script = str(Path(__file__).with_name("akari_simple.py"))
        for text, expected_status in [("3 4\n" + "\n".join(SAMPLE) + "\n", 0),
                                      ("1 2\n.\n", 2)]:
            result = subprocess.run([sys.executable, "-B", script], input=text,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, expected_status, result.stderr)
            if expected_status == 0:
                score = score_board(SAMPLE, tuple(result.stdout.splitlines()[1:]))
                self.assertTrue(score.illuminated)
                self.assertEqual((score.r1, score.r2), (0, 1))
                self.assertEqual(result.stderr, "")
            else:
                self.assertEqual(result.stdout, "")
                self.assertIn("Invalid input", result.stderr)


if __name__ == "__main__":
    unittest.main()

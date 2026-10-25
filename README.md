# Nerdle Generator and Solver

This project generates valid arithmetic equations for a Nerdle-style game and
provides an interactive solver that narrows the possible answers from
Wordle/Nerdle feedback.

The tools use ordinary integer arithmetic, standard operator precedence, and
exact division only. Generated equations contain `+`, `-`, `*`, `/`, and `=`.

## Requirements

- Python 3.8 or newer
- No third-party packages

## Files

| File | Description |
| --- | --- |
| [`nerdle_generator.py`](nerdle_generator.py) | Generates and deduplicates equation patterns. |
| [`nerdle_solver.py`](nerdle_solver.py) | Interactive candidate solver. |
| `solutions_format2_*.json` | Datasets for equations with two operands. |
| `solutions_format3_*.json` | Datasets for equations with three operands. |
| `solutions_format4_*.json` | Datasets for equations with four operands. |

## Quick start

Run the interactive solver from the project directory:

```powershell
python nerdle_solver.py
```

The solver loads these files by default:

```text
solutions_format2_12.json
solutions_format3_12.json
solutions_format4_12.json
```

It expects a 12-character guess and a 12-character feedback string. Enter
feedback using:

- `G` - green: the character is correct and in the correct position
- `Y` - yellow: the character exists but is in the wrong position
- `X` - gray: the character is not present

During a session:

- Enter `q` or press Enter at the guess prompt to quit.
- Enter `r` or `reset` to restore the complete candidate pool.
- After results are displayed, enter a result number to use it as the next
  guess.

Example interaction:

```text
请输入你当前的 12 位猜测等式: 75/3*49=1225
请输入 12 位颜色反馈 (G/Y/X): YYXXXXYYYXXX
```

The solver returns at most 100 exact matches per search and displays at most
20 of them.

Results are sorted by estimated Shannon entropy by default. The interactive
output shows:

- `H`: entropy in bits; higher values indicate that a candidate is expected to
  split the remaining answers into more informative feedback groups.
- `E[剩余]`: the expected number of candidates remaining after the feedback.

Candidates containing `?` are scored by averaging several random valid
instantiations, so their entropy values are estimates. The CLI also displays a
separate ranked list of wildcard patterns for reference.

## Generate datasets

Run the generator with:

```powershell
python nerdle_generator.py
```

The current `__main__` configuration uses:

```python
length = 8
```

and writes:

```text
solutions_format2_8.json
solutions_format3_8.json
solutions_format4_8.json
```

To generate datasets for another equation length, change `length` near the
bottom of [`nerdle_generator.py`](nerdle_generator.py). The output filenames
use that value automatically. The solver's `length` and the dataset suffix
must match; for example, use the `*_12.json` files with `length=12`.

Generation can be computationally expensive for large operand ranges.
Progress is printed while equations are processed.

## Equation generation

`MathWordleGenerator` accepts a target length:

```python
from nerdle_generator import MathWordleGenerator

generator = MathWordleGenerator(target_length=8)
```

Each configuration passed to `generate()` has this shape:

```python
config = {
    "name": "A + B = C",
    "ops": [["+", "-"]],
    "ranges": [(1, 999), (1, 999)],
    "replace_q": ["A", "B", "C"],
    "max_intermediate": 9999,
}
```

Configuration fields:

- `name`: label printed during generation.
- `ops`: one operator list for each operator position. The generator creates
  every combination from those lists.
- `ranges`: inclusive `(minimum, maximum)` ranges for operands `A`, `B`, `C`,
  and `D`.
- `replace_q`: variables whose final digit is replaced with `?` in the saved
  pattern.
- `max_intermediate`: optional absolute limit for intermediate and final
  results. It defaults to `99999`.

For example, the configuration below produces both addition and subtraction
patterns:

```python
{
    "name": "A +/- B = C",
    "ops": [["+", "-"]],
    "ranges": [(1, 999), (1, 999)],
    "replace_q": ["A", "B", "C"],
}
```

The generator applies normal precedence: multiplication and division are
performed before addition and subtraction. Division must be exact, and
division by zero is rejected. Duplicate visible patterns are removed before
the JSON file is written.

## JSON pattern format

Each output file is a JSON array of strings. A pattern can contain `?` where
the generator intentionally hid a final digit:

```json
[
  "2*83=166",
  "7?+608?=615?"
]
```

The solver expands these wildcards while applying feedback and then validates
that the completed string is a mathematically valid equation.

## Using the solver as a library

The solver can also be embedded in another Python script:

```python
from nerdle_solver import MathWordleSolver

solver = MathWordleSolver(
    [
        "solutions_format2_12.json",
        "solutions_format3_12.json",
        "solutions_format4_12.json",
    ],
    length=12,
)

matches = solver.search(
    guess="75/3*49=1225",
    feedback="YYXXXXYYYXXX",
    limit=100,
)

for equation in matches:
    print(equation)
```

`search()` updates the solver's candidate pool cumulatively. Call
`solver.reset()` to discard previous feedback and start over.

### Controlling result ranking

`search()` accepts these ranking-related options:

```python
matches = solver.search(
    guess="75/3*49=1225",
    feedback="YYXXXXYYYXXX",
    limit=100,
    rank=True,
    answer_sample=1000,
    wildcard_samples=3,
    wildcard_limit=100,
)
```

- `rank=True` sorts results by entropy (descending). Set it to `False` to
  return results in lexical order instead.
- `answer_sample` limits the answer sample used to estimate entropy. Larger
  values are more representative but take longer to score.
- `wildcard_samples` controls how many random instantiations are used to score
  each `?` pattern.
- `wildcard_limit` limits how many wildcard patterns are scored for the
  additional reference list. Set it to `0` to disable that list.

For direct access to scores, use `rank_candidates()`:

```python
ranked = solver.rank_candidates(
    candidates,
    answers=solver.last_answer_sample,
)

for item in ranked:
    print(item["candidate"], item["entropy"], item["expected_remaining"])
```

Each ranked item contains `candidate`, `entropy`, `expected_remaining`, and
`estimated`. The `estimated` flag is `True` for wildcard patterns whose score
was calculated from random instantiations.

## Notes

- Paths passed to `MathWordleSolver` are resolved relative to the current
  working directory.
- Missing dataset files produce a warning and are skipped.
- Feedback must contain exactly one character per position in the configured
  equation length.
- The bundled 12-character files are substantially larger than the
  8-character files, so loading or searching them may take noticeable time.

"""Run the launch-time game-data validator without launching.

Both layers, the same ones `czn_optimizer_gui.py` runs: the text/AST
layer that catches syntax errors and duplicate dict keys, and the value
layer that checks ranges, vocabularies and shapes.

The value layer is advisory in the app -- the data still loads and the
scores are simply wrong -- which is exactly why it is worth failing on
here, where nobody is waiting to use the program.
"""

from ._harness import add_source_to_path

NAME = "game data"


def run():
    failures = []
    add_source_to_path()
    import game_data_validator as v

    if not v.check_data_files():
        failures.append(
            "check_data_files() failed: a game_data file has a syntax "
            "error or a duplicate dict key. The app would refuse to start."
        )

    problems = v.find_data_problems()
    for p in problems[:12]:
        failures.append(f"data: {p}")
    if len(problems) > 12:
        failures.append(f"... and {len(problems) - 12} more data problems")
    return failures

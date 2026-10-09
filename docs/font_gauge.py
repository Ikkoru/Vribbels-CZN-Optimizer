"""Run the font gauge at every UI scale, or the ones named.

    python docs/font_gauge.py [125% 150%=1.82 ...]

A scale given as `150%=1.82` is measured at that `tk scaling` in place
of its own (`ui/scaling.trial_text_scaling`): how a candidate for
`TEXT_SCALING` is tried. Each scale is its own launch, rendered and
never shown, on the maintainer's own settings and snapshot (nothing is
written to either); `Vribbels/ui/font_gauge.py` says what is measured
and why those places.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
sys.path.insert(0, str(SOURCE))

from ui import scaling                                        # noqa: E402


def main(argv):
    scales = argv[1:] or list(scaling.SCALE_CHOICES)
    for scale in scales:
        scale, _, trial = scale.partition("=")
        env = dict(os.environ, VRIBBELS_DEV="1", PYTHONIOENCODING="utf-8")
        env.pop("VRIBBELS_TEXT_SCALING", None)
        if trial:
            env["VRIBBELS_TEXT_SCALING"] = trial
        run = subprocess.run(
            [sys.executable, str(SOURCE / "czn_optimizer_gui.py"),
             "--font-gauge", f"--audit-scale={scale}"],
            cwd=HERE.parent, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=900)
        start = run.stdout.find("--- font gauge")
        print(run.stdout[start:] if start >= 0
              else run.stdout[-800:] + run.stderr[-800:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

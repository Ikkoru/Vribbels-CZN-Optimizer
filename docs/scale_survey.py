"""Survey the app at 200% against twice the app at 100%.

    python docs/scale_survey.py [--audit-state=empty|fresh]

Launches the app twice, rendered and never shown, once at each scale
(`Vribbels/ui/scale_survey.py` says what each launch writes), then
writes `_tmp/scale_survey/report.txt` -- every widget whose 200% size is
not twice its 100% one, and every one 200% clips -- and, per tab, the
100% image over the 200% one shrunk to match, in `_tmp/scale_survey/
pairs/`. Without a state it reads the maintainer's own settings and
snapshot, as the audit does; nothing it does writes to either.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
sys.path.insert(0, str(SOURCE))

import audit_states                                           # noqa: E402
from ui import scale_survey                                   # noqa: E402


def main(argv):
    state = audit_states.requested(argv)
    extra = [f"--audit-state={state}"] if state else []
    env = dict(os.environ, VRIBBELS_DEV="1", PYTHONIOENCODING="utf-8")
    for scale in ("100%", "200%"):
        run = subprocess.run(
            [sys.executable, str(SOURCE / "czn_optimizer_gui.py"),
             "--scale-survey", f"--audit-scale={scale}", *extra],
            cwd=HERE.parent, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600)
        said = [line for line in run.stdout.splitlines()
                if line.startswith("scale survey")]
        print("\n".join(said) or run.stdout[-800:] + run.stderr[-800:])
        if not said or "failed" in said[-1]:
            return 1
    low = scale_survey.run_dir(1, state)
    high = scale_survey.run_dir(2, state)
    lines = scale_survey.compare(low, high)
    report = scale_survey.SURVEY_DIR / (
        f"report_{state}.txt" if state else "report.txt")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pairs = scale_survey.side_by_side(
        low, high, scale_survey.SURVEY_DIR / ("pairs_" + state if state
                                              else "pairs"))
    print(lines[0])
    print("\n".join(line for line in lines if line.startswith("==")))
    print(f"report: {report}\n{len(pairs)} side-by-side images beside it")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

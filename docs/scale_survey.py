"""Survey the app at a scale against the app at 100% times that scale.

    python docs/scale_survey.py [--scale=125%|150%|175%|200%]
                                [--audit-state=empty|fresh]

Launches the app twice, rendered and never shown, at 100% and at the
scale asked for -- 200% by default (`Vribbels/ui/scale_survey.py` says
what each launch writes). Then writes `_tmp/scale_survey/report.txt`
-- every widget whose scaled size is not its 100% one times the scale,
and every one the scale clips -- and, per tab, the 100% image over the
scaled one shrunk to match, in `_tmp/scale_survey/pairs/`. Another
scale or a state adds its own suffix to both names. Without a state it
reads the maintainer's own settings and snapshot, as the audit does;
nothing it does writes to either.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
sys.path.insert(0, str(SOURCE))

import audit_states                                           # noqa: E402
from ui import scale_survey, scaling                          # noqa: E402

SCALE_FLAG = "--scale="


def main(argv):
    state = audit_states.requested(argv)
    scale = next((arg[len(SCALE_FLAG):] for arg in argv
                  if arg.startswith(SCALE_FLAG)), "200%")
    if scale not in scaling.SCALE_CHOICES or scale == "100%":
        print(f"{SCALE_FLAG}{scale}: one of "
              f"{', '.join(scaling.SCALE_CHOICES[1:])}")
        return 2
    extra = [f"--audit-state={state}"] if state else []
    env = dict(os.environ, VRIBBELS_DEV="1", PYTHONIOENCODING="utf-8")
    for run_scale in ("100%", scale):
        run = subprocess.run(
            [sys.executable, str(SOURCE / "czn_optimizer_gui.py"),
             "--scale-survey", f"--audit-scale={run_scale}", *extra],
            cwd=HERE.parent, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600)
        said = [line for line in run.stdout.splitlines()
                if line.startswith("scale survey")]
        print("\n".join(said) or run.stdout[-800:] + run.stderr[-800:])
        if not said or "failed" in said[-1]:
            return 1
    low = scale_survey.run_dir(1, state)
    high = scale_survey.run_dir(scaling.parse(scale), state)
    lines = scale_survey.compare(low, high)
    suffix = "".join(f"_{part}" for part in (
        scale.rstrip("%") if scale != "200%" else None, state) if part)
    report = scale_survey.SURVEY_DIR / f"report{suffix}.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pairs = scale_survey.side_by_side(
        low, high, scale_survey.SURVEY_DIR / f"pairs{suffix}")
    print(lines[0])
    print("\n".join(line for line in lines if line.startswith("==")))
    print(f"report: {report}\n{len(pairs)} side-by-side images beside it")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

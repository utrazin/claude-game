"""Run an animation recipe or inspect and validate native bbmodel animations."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools._resolve import resolve_model_target, resolve_recipe
from Tools.recipe_context import recipe_environment
from lib.animation import AnimationEditor, validate_animations


def export_animations(project: str | Path, *, recipe: str | Path | None = None) -> dict:
    project_dir, model = resolve_model_target(project)
    script = resolve_recipe(project, "animation", recipe)
    if not model.is_file():
        return {"status": "fail", "issue": f"Model not found: {model}"}
    if not script.is_file():
        return {"status": "fail", "issue": f"Animation recipe not found: {script}"}
    result = subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT,
                            env=recipe_environment(project),
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        return {"status": "fail", "issue": (result.stderr or result.stdout).strip(),
                "exit_code": result.returncode}
    try:
        summary = validate_animations(json.loads(model.read_text(encoding="utf-8")))
    except Exception as exc:
        return {"status": "fail", "issue": str(exc)}
    if summary["animations"] == 0:
        return {"status": "fail", "issue": "Recipe produced no animations"}
    notes = [line.split("Warning: ", 1)[1].strip() for line in result.stderr.splitlines() if "Warning: " in line]
    return {"status": "pass", "model": str(model), "warnings": notes, **summary}


animation_export = export_animations


def print_inspection(data: dict, rows: int = 30) -> None:
    """Text view of ``inspect_chain``: about ``rows`` evenly spaced samples (--json has all of them)."""
    joints = list(data["frames"][0]["bends"])
    print(f"[inspect] {data['clip']}: {' -> '.join(data['chain'])} length={data['length']} rate={data['rate']}/s")
    print("  time   " + "".join(f"{name + '°':>10}" for name in joints) + "   reach  "
          + "".join(f"{name + ' points':<21}" for name in joints) + "tip                  tip velocity")
    stride = max(1, round(len(data["frames"]) / rows))
    for row in data["frames"][::stride]:
        directions = ""
        for name in joints:
            direction = row["bend_directions"][name]
            directions += ("(" + ",".join(f"{v:5.2f}" for v in direction) + ")  ") if direction else "-" * 19 + "  "
        velocity = row["tip_velocity"]
        velocity = "(" + ",".join(f"{v:6.2f}" for v in velocity) + ")" if velocity else "-"
        print(f"  {row['time']:6.3f} " + "".join(f"{row['bends'][name]:10.1f}" for name in joints)
              + f"   {row['reach']:5.3f}  {directions}({','.join(f'{v:.2f}' for v in row['tip'])})  {velocity}")
    for name, speed in data["joint_speed"].items():
        print(f"  speed {name}: max {speed['max_degrees_per_second']}°/s at {speed['at']}s "
              f"(median {speed['median_degrees_per_second']}°/s), sharpest jerk "
              f"{speed['max_jerk_degrees_per_second']}°/s at {speed['jerk_at']}s")
    for note in data["warnings"]:
        print(f"[inspect] WARN {note}")


def rig_report(editor: AnimationEditor) -> list[dict]:
    """Rest-pose world pivot, local axes (and bone tip/length) of every control, for choosing IK chains,
    targets and the local ``axis`` that ``aim`` turns. ``axes`` maps each local axis to its world direction."""
    rig = editor.rig
    rows = []
    for control in editor.controls():
        node = rig.nodes[control.uuid]
        frame = rig.rest[control.uuid]
        row = {"kind": control.kind, "path": control.path, "pivot": [round(v, 4) for v in frame.origin],
               "axes": {name: [round(frame.linear[i][column], 4) + 0.0 for i in range(3)]
                        for column, name in enumerate("xyz")},
               "children": [editor._control_path(uid) for uid in rig.order
                            if rig.nodes[uid].parent == control.uuid and uid in editor._control_ids]}
        if node.kind == "bone":
            row["tip"] = [round(v, 4) for v in rig.tip(control.uuid, rig.rest)]
            row["length"] = round(node.length or 0.0, 4)
        rows.append(row)
    return rows



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate, inspect, and validate bbmodel animations")
    parser.add_argument("project")
    parser.add_argument("--recipe", help="Recipe relative to the project")
    parser.add_argument("--controls", action="store_true", help="List animatable controls")
    parser.add_argument("--rig", action="store_true",
                        help="List controls with rest world pivots, local axes, bone tips and lengths "
                             "(for IK chains, targets and aim axes)")
    parser.add_argument("--check", action="store_true", help="Validate existing animations without running a recipe")
    parser.add_argument("--inspect", metavar="CLIP",
                        help="Print a saved clip's per-frame numbers for --chain (bends, reach, bend direction, tip)")
    parser.add_argument("--chain", nargs="+", metavar="CONTROL",
                        help="With --inspect: start control and optional end control below it")
    parser.add_argument("--rate", type=int, default=120, help="With --inspect: samples per second (above the keys' fps shows what the viewer interpolates)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.inspect and (not args.chain or len(args.chain) > 2):
        parser.error("--inspect needs --chain START [END]")
    try:
        if args.controls or args.rig or args.check or args.inspect:
            _, model = resolve_model_target(args.project)
            editor = AnimationEditor.from_bbmodel(model)
            if args.controls:
                report = {"status": "pass", "controls": [item.__dict__ for item in editor.controls()]}
            elif args.rig:
                report = {"status": "pass", "rig": rig_report(editor)}
            elif args.inspect:
                report = {"status": "pass", "inspect": editor.inspect_chain(args.inspect, *args.chain, rate=args.rate)}
            else:
                report = {"status": "pass", **validate_animations(json.loads(model.read_text(encoding="utf-8")))}
        else:
            report = export_animations(args.project, recipe=args.recipe)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        report = {"status": "fail", "issue": str(exc)}
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    elif report["status"] == "pass":
        if args.controls:
            for item in report["controls"]:
                print(f"[{item['kind']}] {item['path']} ({item['uuid']})")
        elif args.rig:
            for item in report["rig"]:
                bone = f" tip={tuple(item['tip'])} length={item['length']}" if "tip" in item else ""
                axes = " ".join(f"{name}={tuple(direction)}" for name, direction in item["axes"].items())
                print(f"[{item['kind']}] {item['path']} pivot={tuple(item['pivot'])}{bone} local axes in world: {axes}")
        elif args.inspect:
            print_inspection(report["inspect"])
        else:
            print(f"[animation] PASS animations={report['animations']} controls={report['controls']}")
            for note in report.get("warnings", []):
                print(f"[animation] WARN {note}")
    else:
        print(f"[animation] FAIL {report['issue']}", file=sys.stderr)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

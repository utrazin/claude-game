"""Environment check for a fresh machine: py -3.12 -m Tools.forge doctor [--install] [--smoke] [--json].

Without flags it only inspects and prints what is missing plus the exact command that fixes it.
Nothing is installed unless --install is given AND the user answers "y" to that specific step.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWER_PORT = 8765
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _check(name, status, detail, fix=None, required=True):
    """fix is an argv list (run with cwd=ROOT) or a plain-text hint when it cannot be automated."""
    return {"name": name, "status": status, "detail": detail, "fix": fix, "required": required}


def _version_tuple(text):
    parts = re.findall(r"\d+", text)[:3]
    return tuple(int(part) for part in parts) + (0,) * (3 - len(parts))


def read_requirements(path=None):
    path = Path(path) if path else ROOT / "requirements.txt"
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"([A-Za-z0-9_.\-]+)\s*(?:>=\s*([0-9][0-9.]*))?", line)
        if match:
            out.append((match.group(1), match.group(2) or "0"))
    return out


def check_python():
    version = sys.version_info
    if version >= (3, 12):
        return _check("python", PASS, f"Python {version.major}.{version.minor}.{version.micro} ({sys.executable})")
    return _check("python", FAIL, f"Python {version.major}.{version.minor} is too old; 3.12 is required",
                  "Install Python 3.12 from https://www.python.org/downloads/ (tick the py launcher), then rerun with `py -3.12`.")


def check_py_launcher():
    if sys.platform != "win32":
        return None
    if shutil.which("py") is None:
        return _check("py launcher", WARN, "`py` not found; viewer.bat and the docs use `py -3.12`",
                      "Reinstall Python 3.12 with the 'py launcher' option enabled.", required=False)
    try:
        run = subprocess.run(["py", "-3.12", "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _check("py launcher", WARN, f"`py -3.12` failed: {exc}", required=False)
    if run.returncode == 0:
        return _check("py launcher", PASS, run.stdout.strip() or run.stderr.strip(), required=False)
    return _check("py launcher", WARN, "`py -3.12` is not available; viewer.bat will not start",
                  "Install Python 3.12 from https://www.python.org/downloads/", required=False)


def check_pip_packages():
    results = []
    for name, minimum in read_requirements():
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            results.append(_check(f"pip:{name}", FAIL, f"{name} is not installed (need >={minimum})",
                                  [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]))
            continue
        if _version_tuple(installed) < _version_tuple(minimum):
            results.append(_check(f"pip:{name}", FAIL, f"{name} {installed} is older than >={minimum}",
                                  [sys.executable, "-m", "pip", "install", "-U", "-r", "requirements.txt"]))
        else:
            results.append(_check(f"pip:{name}", PASS, f"{name} {installed}"))
    return results


def check_chromium(smoke=False):
    fix = [sys.executable, "-m", "playwright", "install", "chromium"]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _check("playwright chromium", FAIL, "playwright is not installed, so Chromium cannot be checked", fix)
    try:
        with sync_playwright() as pw:
            executable = Path(pw.chromium.executable_path)
            if not executable.is_file():
                return _check("playwright chromium", FAIL, "Chromium browser binary is not installed", fix)
            if smoke:
                browser = pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
                try:
                    page = browser.new_page()
                    ok = page.evaluate("() => !!document.createElement('canvas').getContext('webgl')")
                finally:
                    browser.close()
                if not ok:
                    return _check("playwright chromium", FAIL, "Chromium launched but WebGL is unavailable (captures need it)",
                                  "Update GPU drivers or run `py -3.12 -m playwright install chromium` again.")
                return _check("playwright chromium", PASS, f"launched headless with WebGL ({executable.name})")
            return _check("playwright chromium", PASS, f"installed ({executable})")
    except Exception as exc:  # playwright raises its own error types
        return _check("playwright chromium", FAIL, f"could not inspect Chromium: {str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__}", fix)


def check_node():
    node = shutil.which("node")
    if node is None:
        return [_check("node", WARN, "node not found; only needed for glTF export validation (tests and `export` checks)",
                       ["winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e"] if shutil.which("winget") else
                       "Install Node.js LTS from https://nodejs.org/", required=False)]
    run = subprocess.run([node, "--version"], capture_output=True, text=True)
    results = [_check("node", PASS, run.stdout.strip(), required=False)]
    if (ROOT / "node_modules" / "gltf-validator").is_dir():
        results.append(_check("npm:gltf-validator", PASS, "installed", required=False))
    else:
        npm = shutil.which("npm")
        fix = [npm, "ci"] if npm and (ROOT / "package-lock.json").is_file() else (
            [npm, "install"] if npm else "Install npm (ships with Node.js), then run `npm ci` in the repository root.")
        results.append(_check("npm:gltf-validator", WARN, "node_modules/gltf-validator is missing; GLB validation tests will be skipped",
                              fix, required=False))
    return results


def check_port(port=VIEWER_PORT):
    try:
        from Tools.viewer_server import probe_health
        health = probe_health(port=port)
    except Exception:
        health = None
    if health:
        return _check("viewer port", PASS, f"{port} already serves a Forge viewer (mode {health.get('mode')}); "
                      "single-project viewers use 8080 by default", required=False)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return _check("viewer port", WARN, f"port {port} is taken by another program; the global viewer will use the next free port",
                          required=False)
    return _check("viewer port", PASS, f"{port} is free (global viewer; single-project viewers use 8080 by default)", required=False)


def check_writable():
    results = []
    for rel in ("projects", ".runtime/checks"):
        target = ROOT / rel
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / ".doctor-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            results.append(_check(f"write:{rel}", PASS, "writable"))
        except OSError as exc:
            results.append(_check(f"write:{rel}", FAIL, f"not writable: {exc}",
                                  "Move the repository to a folder you can write to (not Program Files)."))
    return results


def run_checks(smoke=False, port=VIEWER_PORT):
    checks = [check_python()]
    launcher = check_py_launcher()
    if launcher:
        checks.append(launcher)
    checks += check_pip_packages()
    checks.append(check_chromium(smoke))
    checks += check_node()
    checks.append(check_port(port))
    checks += check_writable()
    return checks


def _confirm(question):
    if not sys.stdin or not sys.stdin.isatty():
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes", "s", "sim")


def apply_fixes(checks, confirm=_confirm, runner=subprocess.run):
    """Run each distinct automatable fix only after confirm() approves that exact command."""
    done, ran = set(), []
    for item in checks:
        fix = item["fix"]
        if item["status"] == PASS or not isinstance(fix, list):
            continue
        key = tuple(fix)
        if key in done:
            continue
        done.add(key)
        command = display_command(fix)
        if not confirm(f"Run `{command}` to fix {item['name']}?"):
            print(f"[doctor] skipped: {command}")
            continue
        result = runner(fix, cwd=ROOT)
        ran.append((command, result.returncode))
    return ran


def display_command(fix):
    """Show `npm ci`, not the machine-specific path the command resolves to."""
    parts = [str(p) for p in fix]
    if parts and Path(parts[0]).is_absolute():
        parts[0] = Path(parts[0]).stem
    return " ".join(parts)


def format_report(checks):
    marks = {PASS: "ok  ", WARN: "warn", FAIL: "FAIL"}
    lines = []
    for item in checks:
        lines.append(f"[{marks[item['status']]}] {item['name']}: {item['detail']}")
        if item["status"] != PASS and item["fix"]:
            hint = display_command(item["fix"]) if isinstance(item["fix"], list) else item["fix"]
            lines.append(f"       fix: {hint}")
    return "\n".join(lines)


def verdict(checks):
    return not any(item["status"] == FAIL and item["required"] for item in checks)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check (and optionally install) what this machine needs to run Forge.")
    parser.add_argument("--install", action="store_true", help="Offer each fix and run it only after you answer y")
    parser.add_argument("--smoke", action="store_true", help="Launch headless Chromium and confirm WebGL works")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--port", type=int, default=VIEWER_PORT)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    checks = run_checks(smoke=args.smoke, port=args.port)
    if args.json:
        print(json.dumps({"ok": verdict(checks), "checks": checks}, indent=2))
        return 0 if verdict(checks) else 1
    print(format_report(checks))
    if args.install and any(c["status"] != PASS and isinstance(c["fix"], list) for c in checks):
        if not (sys.stdin and sys.stdin.isatty()):
            print("[doctor] --install needs an interactive terminal; nothing was installed. Run the fix commands above yourself.")
        else:
            ran = apply_fixes(checks)
            if ran:
                checks = run_checks(smoke=args.smoke, port=args.port)
                print("\n[doctor] after installing:")
                print(format_report(checks))
    ok = verdict(checks)
    print("\n[doctor] " + ("ready" if ok else "NOT ready: fix the FAIL items above (rerun with --install to be offered each fix)."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

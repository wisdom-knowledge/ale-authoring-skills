"""Check readers; optionally provision pinned wheels in a task-owned venv."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import time


MANIFEST = Path(__file__).resolve().parents[1] / "references" / "reader-profiles.json"
OWNER = {"owner": "ale-rubric-builder", "schema_version": 1}
NATIVE_TOOLS = (
    "soffice", "libreoffice", "blender", "FreeCADCmd", "freecadcmd",
    "kicad-cli", "inkscape", "ffmpeg", "ffprobe", "tesseract", "ODAFileConverter",
)
PACKAGE_MANAGERS = ("winget", "apt-get", "brew")
PROBE = r'''
import contextlib, importlib, importlib.metadata as md, io, json, site, sys
packages = json.loads(sys.argv[1])
result = {"executable": sys.executable, "prefix": sys.prefix,
          "base_prefix": sys.base_prefix, "site_packages": site.getsitepackages(),
          "packages": {}}
for name, spec in packages.items():
    entry = {"required": spec["version"], "installed": None, "state": "missing"}
    try:
        entry["installed"] = md.version(name)
        with contextlib.redirect_stdout(io.StringIO()):
            importlib.import_module(spec["module"])
        entry["state"] = "ok" if entry["installed"] == spec["version"] else "version_mismatch"
    except md.PackageNotFoundError:
        pass
    except Exception as exc:
        entry["state"] = "import_error"
        entry["error"] = type(exc).__name__ + ": " + str(exc)
    result["packages"][name] = entry
print(json.dumps(result))
'''


def load_manifest(path=MANIFEST):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["schema_version"] != 1:
        raise ValueError("Unsupported reader manifest")
    for name, spec in data["packages"].items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ValueError("Invalid package name")
        if not re.fullmatch(r"\d+(?:\.\d+)+", spec["version"]):
            raise ValueError("Every package must have an exact release pin")
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", spec["module"]):
            raise ValueError("Invalid import module")
    for names in data["profiles"].values():
        if not names or any(name not in data["packages"] for name in names):
            raise ValueError("Profile has an unknown or empty dependency list")
    return data


def select_packages(manifest, profiles):
    unknown = set(profiles) - manifest["profiles"].keys()
    if unknown:
        raise ValueError("Unknown profiles: " + ", ".join(sorted(unknown)))
    names = {name for profile in profiles for name in manifest["profiles"][profile]}
    return {name: manifest["packages"][name] for name in sorted(names)}


def clean_env():
    # Ignore host pip indexes, targets and Python search-path overrides.
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PIP_", "PYTHON"))}
    env["PIP_CONFIG_FILE"] = os.devnull
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(command, timeout=90):
    return subprocess.run([str(part) for part in command], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          env=clean_env(), timeout=timeout, check=False)


def probe(python, packages):
    process = run([python, "-I", "-B", "-X", "utf8", "-c", PROBE, json.dumps(packages)])
    if process.returncode:
        raise RuntimeError("Reader probe failed: " + process.stderr[-2000:])
    return json.loads(process.stdout)


def readers_ready(result):
    return all(entry["state"] == "ok" for entry in result["packages"].values())


def checked_child(root, path):
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise ValueError("Refusing linked runtime path: " + str(path))
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Runtime path escapes work directory")
    return path


def runtime_path(work_dir):
    root = work_dir.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("work-dir must be an existing session directory")
    runtime = checked_child(root, root / ".ale-rubric-runtime")
    if runtime.exists():
        marker = checked_child(runtime, runtime / "owner.json")
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")) != OWNER:
            raise ValueError("Refusing a runtime directory not owned by this Skill")
    return runtime


def managed_python(runtime):
    venv = checked_child(runtime, runtime / "venv")
    if not venv.exists():
        return None
    config = checked_child(venv, venv / "pyvenv.cfg")
    if not config.is_file():
        raise ValueError("Incomplete runtime venv; use a fresh session work directory")
    settings = dict(line.split("=", 1) for line in config.read_text(encoding="utf-8").splitlines()
                    if "=" in line)
    settings = {key.strip(): value.strip().lower() for key, value in settings.items()}
    if settings.get("include-system-site-packages") != "false":
        raise ValueError("Runtime venv must not include system site-packages")
    executable_dir = checked_child(venv, venv / ("Scripts" if os.name == "nt" else "bin"))
    python = executable_dir / ("python.exe" if os.name == "nt" else "python")
    info = probe(python, {})
    if Path(info["prefix"]).resolve() != venv.resolve() or info["prefix"] == info["base_prefix"]:
        raise ValueError("Managed interpreter does not belong to runtime venv")
    if any(not Path(path).resolve().is_relative_to(venv.resolve()) for path in info["site_packages"]):
        raise ValueError("Runtime site-packages escapes venv")
    return python


@contextmanager
def install_lock(runtime):
    lock = checked_child(runtime, runtime / "install.lock")
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        lock.unlink()


def pip_command(python, packages, report, force_reinstall=False):
    return [str(python), "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check",
            "install", "--index-url", "https://pypi.org/simple", "--only-binary=:all:",
            "--no-deps", "--no-input", "--no-cache-dir", "--timeout", "30", "--retries", "1",
            "--report", str(report),
            *(["--force-reinstall"] if force_reinstall else []),
            *[name + "==" + spec["version"] for name, spec in packages.items()]]


def provision(runtime, packages, minimum):
    if platform.python_implementation() != "CPython" or sys.version_info[:2] < tuple(minimum):
        raise ValueError("Pinned readers require CPython " + ".".join(map(str, minimum)) + "+")
    if struct.calcsize("P") != 8:
        raise ValueError("Pinned readers require 64-bit Python")
    if not packages:
        raise ValueError("Select at least one profile before installing")
    if not runtime.exists():
        runtime.mkdir()
        (runtime / "owner.json").write_text(json.dumps(OWNER), encoding="utf-8")
    with install_lock(runtime):
        python = managed_python(runtime)
        if python is None:
            creation = run([sys.executable, "-I", "-B", "-m", "venv", runtime / "venv"], timeout=180)
            if creation.returncode:
                raise RuntimeError("venv creation failed; check Python venv/ensurepip support: "
                                   + creation.stderr[-2000:])
            python = managed_python(runtime)
        before = probe(python, packages)
        installed = not readers_ready(before)
        install_report = None
        if installed:
            install_report = runtime / ("pip-install-" + str(time.time_ns()) + ".json")
            log = install_report.with_suffix(".log")
            broken = any(entry["state"] == "import_error" for entry in before["packages"].values())
            try:
                process = run(pip_command(python, packages, install_report, broken), timeout=600)
            except subprocess.TimeoutExpired as exc:
                output = []
                for text in (exc.stdout, exc.stderr):
                    output.append(text.decode("utf-8", errors="replace") if isinstance(text, bytes) else text or "")
                log.write_text("".join(output) + "\nInstallation timed out.\n", encoding="utf-8")
                raise RuntimeError("Pinned wheel installation timed out; see " + str(log)) from exc
            log.write_text(process.stdout + process.stderr, encoding="utf-8")
            if process.returncode:
                raise RuntimeError("Pinned wheel installation failed; see " + str(log))
        after = probe(python, packages)
        check = run([python, "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check", "check"])
        inventory = run([python, "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check",
                         "list", "--format=json"])
        if inventory.returncode:
            raise RuntimeError("Could not record installed package inventory")
        receipt = {"manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                   "requested_packages": packages, "probe": after,
                   "pip_check": {"exit_code": check.returncode, "output": check.stdout + check.stderr},
                   "installed_packages": json.loads(inventory.stdout),
                   "install_performed": installed,
                   "install_report": str(install_report) if install_report else None}
        receipt_path = checked_child(runtime, runtime / "environment.json")
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        if not readers_ready(after) or check.returncode:
            raise RuntimeError("Reader verification failed; see " + str(receipt_path))
        return python, after, receipt


def main(argv=None):
    manifest = load_manifest()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True,
                        help="Existing session work directory, not a source/production directory")
    parser.add_argument("--profiles", nargs="*", choices=sorted(manifest["profiles"]), default=[])
    parser.add_argument("--install", action="store_true", help="Provision only in the Skill-owned venv")
    args = parser.parse_args(argv)
    result = {"status": "BLOCKED", "profiles": args.profiles,
              "host": {"system": platform.system(), "machine": platform.machine(),
                       "python": platform.python_version(), "executable": sys.executable},
              "native_tools_on_path": {name: shutil.which(name) for name in NATIVE_TOOLS},
              "package_managers_on_path": {name: shutil.which(name) for name in PACKAGE_MANAGERS},
              "file_read_verified": False}
    try:
        runtime = runtime_path(args.work_dir)
        packages = select_packages(manifest, args.profiles)
        if args.install:
            python, info, receipt = provision(runtime, packages, manifest["python_minimum"])
            result.update(install_performed=receipt["install_performed"],
                          install_report=receipt["install_report"], receipt=str(runtime / "environment.json"))
        else:
            python = managed_python(runtime) or Path(sys.executable)
            info = probe(python, packages)
        result.update(python=str(python), probe=info,
                      runtime_origin="managed" if Path(info["prefix"]).resolve() == runtime / "venv" else "host")
        result["status"] = "READY" if readers_ready(info) else "NEEDS_DEPENDENCIES"
        if not packages:
            result["status"] = "INVENTORY_ONLY"
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] in ("READY", "INVENTORY_ONLY") else 2


if __name__ == "__main__":
    raise SystemExit(main())

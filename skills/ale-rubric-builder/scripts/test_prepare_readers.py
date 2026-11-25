"""Offline regression tests for scoped, pinned reader provisioning."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import prepare_readers as readers


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / ".ale-rubric-runtime"
        self.manifest = readers.load_manifest()
        self.packages = readers.select_packages(self.manifest, ["xls"])

    def own_runtime(self):
        self.runtime.mkdir()
        (self.runtime / "owner.json").write_text(json.dumps(readers.OWNER), encoding="utf-8")

    def info(self, state="ok"):
        return {"packages": {name: {"state": state, "installed": spec["version"]}
                             for name, spec in self.packages.items()}}

    def cli(self, *args, script=None, cwd=None):
        return subprocess.run([sys.executable, "-I", "-B", "-X", "utf8",
                               str(script or Path(readers.__file__)),
                               "--work-dir", str(self.root), *args],
                              cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False)

    def test_all_packages_are_pinned_and_used(self):
        used = {name for group in self.manifest["profiles"].values() for name in group}
        self.assertEqual(used, set(self.manifest["packages"]))
        for spec in self.manifest["packages"].values():
            self.assertRegex(spec["version"], r"^\d+(\.\d+)+$")

    def test_only_selected_profile_closure(self):
        self.assertEqual(set(self.packages), {"xlrd"})
        dxf = readers.select_packages(self.manifest, ["dxf", "image"])
        self.assertEqual(set(dxf), {"ezdxf", "numpy", "fonttools", "pyparsing",
                                    "typing-extensions", "PyMuPDF", "Pillow"})

    def test_unknown_profile_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown profiles"):
            readers.select_packages(self.manifest, ["https://untrusted/package"])
        self.assertNotEqual(self.cli("--profiles", "not-a-profile").returncode, 0)
        self.assertFalse(self.runtime.exists())

    def test_inventory_cli_is_read_only(self):
        before = list(self.root.rglob("*"))
        process = self.cli()
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        output = json.loads(process.stdout)
        self.assertEqual(output["status"], "INVENTORY_ONLY")
        self.assertFalse(output["file_read_verified"])
        self.assertEqual(before, list(self.root.rglob("*")))

    def test_missing_and_broken_import_are_not_ready(self):
        for state in ("missing", "version_mismatch", "import_error"):
            self.assertFalse(readers.readers_ready(self.info(state)))
        self.assertTrue(readers.readers_ready(self.info()))

    def test_probe_really_imports_module(self):
        packages = {"pip": {"version": "0.0.0", "module": "_ale_nonexistent_reader_"}}
        result = readers.probe(sys.executable, packages)
        self.assertEqual(result["packages"]["pip"]["state"], "import_error")

    def test_probe_missing_distribution(self):
        result = readers.probe(sys.executable, {"ale-nonexistent-dist-123": {"version": "1.0", "module": "json"}})
        self.assertEqual(result["packages"]["ale-nonexistent-dist-123"]["state"], "missing")

    def test_pip_command_is_pinned_binary_and_isolated(self):
        command = readers.pip_command(self.root / "venv-python", self.packages, self.root / "report.json")
        self.assertEqual(command[0], str(self.root / "venv-python"))
        self.assertIn("--isolated", command)
        self.assertIn("--no-deps", command)
        self.assertIn("--only-binary=:all:", command)
        self.assertIn("--no-cache-dir", command)
        self.assertIn("--timeout", command)
        self.assertIn("--retries", command)
        self.assertIn("xlrd==2.0.2", command)
        self.assertEqual(command[command.index("--index-url") + 1], "https://pypi.org/simple")
        for forbidden in ("--user", "--target", "--prefix", "--extra-index-url", "--trusted-host"):
            self.assertNotIn(forbidden, command)

    def test_host_pip_and_python_overrides_are_removed(self):
        with patch.dict(os.environ, {"PIP_INDEX_URL": "https://untrusted/", "PIP_TARGET": "elsewhere",
                                     "PYTHONPATH": "elsewhere", "PIP_EXTRA_INDEX_URL": "https://untrusted/"}):
            env = readers.clean_env()
        self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)
        for name in ("PIP_INDEX_URL", "PIP_TARGET", "PYTHONPATH", "PIP_EXTRA_INDEX_URL"):
            self.assertNotIn(name, env)

    def test_foreign_runtime_is_not_overwritten(self):
        self.runtime.mkdir()
        marker = self.runtime / "keep.txt"
        marker.write_text("untouched", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not owned"):
            readers.runtime_path(self.root)
        self.assertEqual(marker.read_text(), "untouched")

    def test_foreign_owner_rejected(self):
        self.own_runtime()
        (self.runtime / "owner.json").write_text('{"owner":"other"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not owned"):
            readers.runtime_path(self.root)

    def test_escaping_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "escapes"):
            readers.checked_child(self.root, self.root / ".." / "outside")

    def test_linked_runtime_rejected(self):
        other = self.root / "other"
        other.mkdir()
        try:
            self.runtime.symlink_to(other, target_is_directory=True)
        except OSError:
            self.skipTest("OS does not permit creating test symlinks")
        with self.assertRaisesRegex(ValueError, "linked"):
            readers.runtime_path(self.root)

    def test_incomplete_venv_rejected(self):
        self.own_runtime()
        (self.runtime / "venv").mkdir()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            readers.managed_python(self.runtime)

    def test_shared_site_packages_rejected(self):
        self.own_runtime()
        venv = self.runtime / "venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("include-system-site-packages = true", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "system site-packages"):
            readers.managed_python(self.runtime)

    def test_wrong_interpreter_prefix_rejected(self):
        self.own_runtime()
        venv = self.runtime / "venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("include-system-site-packages = false", encoding="utf-8")
        with patch.object(readers, "probe", return_value={"prefix": str(self.root), "base_prefix": "other"}):
            with self.assertRaisesRegex(ValueError, "does not belong"):
                readers.managed_python(self.runtime)

    def fake_run(self, command, timeout=90):
        stdout = "[]" if "list" in command else "No broken requirements found."
        return subprocess.CompletedProcess(command, 0, stdout, "")

    def test_provision_already_ready_does_not_install(self):
        with patch.object(readers, "managed_python", return_value=self.root / "managed-python"), \
             patch.object(readers, "probe", return_value=self.info()), \
             patch.object(readers, "run", side_effect=self.fake_run) as runner:
            _, _, receipt = readers.provision(self.runtime, self.packages, [3, 12])
        self.assertFalse(receipt["install_performed"])
        self.assertFalse(any("install" in call.args[0] for call in runner.call_args_list))
        self.assertTrue((self.runtime / "environment.json").is_file())
        self.assertFalse((self.runtime / "install.lock").exists())

    def test_provision_missing_installs_and_rechecks(self):
        python = self.root / "managed-python"
        with patch.object(readers, "managed_python", return_value=python), \
             patch.object(readers, "probe", side_effect=[self.info("missing"), self.info()]), \
             patch.object(readers, "run", side_effect=self.fake_run) as runner:
            _, _, receipt = readers.provision(self.runtime, self.packages, [3, 12])
        installs = [call.args[0] for call in runner.call_args_list if "install" in call.args[0]]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0][0], str(python))
        self.assertTrue(receipt["install_performed"])
        self.assertTrue(any("check" in call.args[0] for call in runner.call_args_list))

    def test_pip_failure_stops_and_keeps_log(self):
        with patch.object(readers, "managed_python", return_value=self.root / "managed-python"), \
             patch.object(readers, "probe", return_value=self.info("missing")), \
             patch.object(readers, "run", return_value=subprocess.CompletedProcess([], 1, "", "No wheel")) as runner:
            with self.assertRaisesRegex(RuntimeError, "installation failed"):
                readers.provision(self.runtime, self.packages, [3, 12])
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(len(list(self.runtime.glob("pip-install-*.log"))), 1)
        self.assertFalse((self.runtime / "install.lock").exists())

    def test_no_install_without_profile(self):
        process = self.cli("--install")
        self.assertEqual(process.returncode, 2)
        self.assertFalse(self.runtime.exists())

    def test_broken_import_forces_one_reinstall(self):
        with patch.object(readers, "managed_python", return_value=self.root / "managed-python"), \
             patch.object(readers, "probe", side_effect=[self.info("import_error"), self.info()]), \
             patch.object(readers, "run", side_effect=self.fake_run) as runner:
            readers.provision(self.runtime, self.packages, [3, 12])
        installs = [call.args[0] for call in runner.call_args_list if "install" in call.args[0]]
        self.assertEqual(len(installs), 1)
        self.assertIn("--force-reinstall", installs[0])

    def test_install_timeout_keeps_log_and_releases_lock(self):
        with patch.object(readers, "managed_python", return_value=self.root / "managed-python"), \
             patch.object(readers, "probe", return_value=self.info("missing")), \
             patch.object(readers, "run", side_effect=subprocess.TimeoutExpired("pip", 600, output=b"partial")):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                readers.provision(self.runtime, self.packages, [3, 12])
        self.assertFalse((self.runtime / "install.lock").exists())
        logs = list(self.runtime.glob("pip-install-*.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn("partial", logs[0].read_text(encoding="utf-8"))

    def test_pip_check_failure_is_not_ready(self):
        def broken_check(command, timeout=90):
            if "check" in command:
                return subprocess.CompletedProcess(command, 1, "Missing transitive dependency", "")
            return self.fake_run(command, timeout)

        with patch.object(readers, "managed_python", return_value=self.root / "managed-python"), \
             patch.object(readers, "probe", return_value=self.info()), \
             patch.object(readers, "run", side_effect=broken_check):
            with self.assertRaisesRegex(RuntimeError, "verification failed"):
                readers.provision(self.runtime, self.packages, [3, 12])
        receipt = json.loads((self.runtime / "environment.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["pip_check"]["exit_code"], 1)

    def test_concurrent_install_rejected(self):
        self.own_runtime()
        with readers.install_lock(self.runtime):
            with self.assertRaises(FileExistsError):
                with readers.install_lock(self.runtime):
                    self.fail("Concurrent installation entered")

    def test_portable_from_unrelated_directory(self):
        package = self.root / "relocated skill"
        shutil.copytree(Path(readers.__file__).resolve().parents[1], package,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        work = self.root / "unrelated \u6750\u6599"
        work.mkdir()
        process = self.cli("--profiles", "xls", script=package / "scripts" / "prepare_readers.py", cwd=work)
        self.assertIn(process.returncode, (0, 2), process.stderr)
        output = json.loads(process.stdout)
        self.assertEqual(set(output["probe"]["packages"]), {"xlrd"})
        self.assertFalse(self.runtime.exists())
        self.assertEqual(list(work.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

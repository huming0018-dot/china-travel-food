"""No Docker, SSH, production filesystem or network calls; entry wiring only."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class ReleaseEntry(unittest.TestCase):
    def fixture(self, fail_build=False, missing_inputs=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, build, bins = root / "repo", root / "build", root / "bin"
            (source / ".git").mkdir(parents=True)
            (source / "cloud/vendor/pipeline").mkdir(parents=True)
            (source / "cloud/external_watchdog").mkdir()
            (source / "cloud/vendor/pipeline/fixture.py").touch()
            (source / "cloud/fixture.py").touch()
            for name in ("build_model_image.sh", "install_model_access.sh"):
                (source / "cloud" / name).write_text("# fixture only\n")
            bins.mkdir()
            log = root / "commands"
            scripts = {
                "git": "#!/bin/sh\ncase \"$*\" in *rev-parse*) echo fixture;; esac\n",
                "rsync": "#!/bin/sh\nexit 0\n",
                "sleep": "#!/bin/sh\nexit 0\n",
                "sudo": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n'
                        'case "$*" in *build_model_image.sh*) exit "$BUILD_EXIT";; esac\nexit 0\n',
            }
            for name, content in scripts.items():
                path = bins / name
                path.write_text(content)
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(bins) + os.pathsep + os.environ["PATH"],
                       FOOD_SRC_CACHE=str(source), FOOD_BUILD_DIR=str(build),
                       CALL_LOG=str(log), BUILD_EXIT="9" if fail_build else "0",
                       MODEL_WHEELHOUSE=str(root / "private-wheels"),
                       MODEL_ACCESS_WHEEL_SHA256="a" * 64)
            if missing_inputs:
                env.pop("MODEL_WHEELHOUSE")
            result = subprocess.run(["bash", str(HERE / "build_sync.sh")],
                                    env=env, text=True, capture_output=True)
            calls = log.read_text() if log.exists() else ""
            copied = all((build / name).exists() for name in
                         ("build_model_image.sh", "install_model_access.sh"))
            return result, calls, copied

    def test_success_wires_scripts_and_explicit_build_inputs(self):
        result, calls, copied = self.fixture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(copied)
        self.assertIn("MODEL_WHEELHOUSE=", calls)
        self.assertIn("MODEL_ACCESS_WHEEL_SHA256=" + "a" * 64, calls)
        self.assertLess(calls.index("build_model_image.sh"), calls.index("docker compose up"))

    def test_failed_build_never_replaces_service(self):
        result, calls, _ = self.fixture(fail_build=True)
        self.assertEqual(result.returncode, 9)
        self.assertNotIn("docker compose", calls)

    def test_missing_inputs_never_invokes_docker(self):
        result, calls, _ = self.fixture(missing_inputs=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, "")

    def test_legacy_server_entry_exits_before_external_actions(self):
        result = subprocess.run(["bash", str(HERE / "build_on_server.sh")],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("legacy deployment entry is disabled", result.stderr)
        self.assertNotIn("==>", result.stdout)


if __name__ == "__main__":
    unittest.main()

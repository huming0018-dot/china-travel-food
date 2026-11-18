"""Offline build-entry checks with a synthetic package, not private model source."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import venv
import zipfile

HERE = Path(__file__).resolve().parent


class BuildEntry(unittest.TestCase):
    def run_fixture(self, *, bad_hash=False, missing_dependency=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wheels = root / "wheels"
            wheels.mkdir()
            wheel = wheels / "agent_model_access-0.1.0-py3-none-any.whl"
            info = "agent_model_access-0.1.0.dist-info"
            metadata = "Metadata-Version: 2.1\nName: agent-model-access\nVersion: 0.1.0\n"
            if missing_dependency:
                metadata += "Requires-Dist: unavailable-model-build-fixture==0.0.1\n"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("agent_model_access/__init__.py",
                                 "def create_client(): return 'synthetic-build-fixture'\n")
                archive.writestr(info + "/METADATA", metadata)
                archive.writestr(info + "/WHEEL",
                                 "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
                archive.writestr(info + "/RECORD", "")
            digest = "0" * 64 if bad_hash else hashlib.sha256(wheel.read_bytes()).hexdigest()
            envdir = root / "venv"
            venv.EnvBuilder(with_pip=True).create(envdir)
            env = dict(os.environ, PATH=str(envdir / "bin") + os.pathsep + os.environ["PATH"],
                       PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1")
            result = subprocess.run(["sh", str(HERE / "install_model_access.sh"), str(wheels), digest],
                                    env=env, cwd=root, text=True, capture_output=True)
            probe = subprocess.run([str(envdir / "bin/python"), "-I", "-c",
                                    "from agent_model_access import create_client; "
                                    "assert create_client() == 'synthetic-build-fixture'"],
                                   cwd=root, text=True, capture_output=True)
            return result, probe

    def test_fixed_wheel_installs_offline(self):
        result, probe = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(probe.returncode, 0, probe.stderr)

    def test_wrong_hash_blocks_install(self):
        result, probe = self.run_fixture(bad_hash=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(probe.returncode, 0)

    def test_missing_dependency_fails_without_network_fallback(self):
        result, probe = self.run_fixture(missing_dependency=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No matching distribution", result.stderr)
        self.assertNotEqual(probe.returncode, 0)

    def test_docker_invokes_verified_offline_entry(self):
        dockerfile = (HERE / "Dockerfile").read_text()
        self.assertIn("from=model_wheels,target=/model-wheels", dockerfile)
        self.assertIn('sh /app/cloud/install_model_access.sh /model-wheels "$MODEL_ACCESS_WHEEL_SHA256"', dockerfile)


if __name__ == "__main__":
    unittest.main()

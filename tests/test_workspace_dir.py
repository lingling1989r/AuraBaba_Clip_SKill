import os
import tempfile
import unittest
from pathlib import Path

from clipclipskill import cli
from clipclipskill.workspace import (
    WORKSPACE_ENV_VAR,
    WORKSPACE_CONFIG_PATH,
    create_job_workspace,
    get_job_workspace,
    read_workspace_binding,
    resolve_jobs_root,
)


class WorkspaceDirTests(unittest.TestCase):
    def tearDown(self):
        WORKSPACE_CONFIG_PATH.unlink(missing_ok=True)

    def test_create_job_workspace_uses_explicit_base_dir(self):
        with tempfile.TemporaryDirectory() as workspace_dir:
            workspace = create_job_workspace("job-a", workspace_dir)
            self.assertEqual(workspace.jobs_root, Path(workspace_dir).resolve())
            self.assertEqual(workspace.root, Path(workspace_dir).resolve() / "job-a")
            self.assertTrue(workspace.status_path.parent.exists())

    def test_get_job_workspace_uses_environment_variable(self):
        with tempfile.TemporaryDirectory() as workspace_dir:
            original = os.environ.get(WORKSPACE_ENV_VAR)
            try:
                os.environ[WORKSPACE_ENV_VAR] = workspace_dir
                jobs_root = resolve_jobs_root()
                workspace = get_job_workspace("job-b")
                self.assertEqual(jobs_root, Path(workspace_dir).resolve())
                self.assertEqual(workspace.root, Path(workspace_dir).resolve() / "job-b")
            finally:
                if original is None:
                    os.environ.pop(WORKSPACE_ENV_VAR, None)
                else:
                    os.environ[WORKSPACE_ENV_VAR] = original

    def test_bind_workspace_persists_default_directory(self):
        with tempfile.TemporaryDirectory() as workspace_dir:
            result = cli.cmd_bind_workspace(type("Args", (), {"directory": workspace_dir})())
            self.assertEqual(result, 0)
            self.assertEqual(read_workspace_binding(), Path(workspace_dir).resolve())
            self.assertEqual(resolve_jobs_root(), Path(workspace_dir).resolve())

    def test_unbind_workspace_clears_default_directory(self):
        with tempfile.TemporaryDirectory() as workspace_dir:
            cli.cmd_bind_workspace(type("Args", (), {"directory": workspace_dir})())
            result = cli.cmd_unbind_workspace(type("Args", (), {})())
            self.assertEqual(result, 0)
            self.assertIsNone(read_workspace_binding())


if __name__ == "__main__":
    unittest.main()

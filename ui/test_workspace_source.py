"""Dependency-free contract checks for the optional GTK4 workspace client."""
from pathlib import Path
import unittest


SOURCE = Path(__file__).with_name("pocket_rocket_workspace.c").read_text(encoding="utf-8")


class WorkspaceSourceContract(unittest.TestCase):
    def test_local_routes_are_explicit(self):
        self.assertIn('"/ask"', SOURCE)
        self.assertIn('"/reset"', SOURCE)
        self.assertIn('"127.0.0.1"', SOURCE)


    def test_subprocesses_do_not_use_shell_interpolation(self):
        self.assertIn("execvp(", SOURCE)
        self.assertNotIn("system(", SOURCE)
        self.assertNotIn("popen(", SOURCE)
        self.assertNotIn("sh -c", SOURCE)


    def test_workspace_has_real_actions(self):
        for action in ("on_ask", "on_reset", "on_save", "on_git_status", "on_git_diff",
                       "on_git_stage", "on_git_unstage", "on_git_commit", "on_make_test",
                       "on_record_task"):
            self.assertIn(action, SOURCE)

    def test_save_is_bounded_and_atomic(self):
        for operation in ("safe_writable_file", "atomic_save_text", "g_utf8_validate",
                          "fchmod", "fsync", "rename", "memchr", "Confirm save"):
            self.assertIn(operation, SOURCE)
        self.assertIn("MAX_FILE_BYTES", SOURCE)

    def test_git_mutations_require_explicit_commit_confirmation(self):
        self.assertIn('"git", "add", "--"', SOURCE)
        self.assertIn('"git", "restore", "--staged", "--"', SOURCE)
        self.assertIn('"git", "commit", "-m"', SOURCE)
        self.assertIn("Confirm commit", SOURCE)


    def test_no_model_or_cloud_client_is_embedded(self):
        self.assertNotIn("transformers", SOURCE.lower())
        self.assertNotIn("https://", SOURCE.lower())


if __name__ == "__main__":
    unittest.main()

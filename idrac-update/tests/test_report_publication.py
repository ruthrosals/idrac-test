from __future__ import annotations

import importlib.util
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_report_snapshot.py"
spec = importlib.util.spec_from_file_location("publish_report_snapshot", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ReportRetentionTests(unittest.TestCase):
    def test_four_prefixes_retains_latest_three(self) -> None:
        kept, deleted = module.retention_plan(
            [
                "20260715-135254/",
                "20260715-135502/",
                "20260715-135735/",
                "20260715-140120/",
            ],
            3,
            "20260715-140120",
        )
        self.assertEqual(deleted, ["20260715-135254/"])
        self.assertEqual(
            kept,
            ["20260715-135502/", "20260715-135735/", "20260715-140120/"],
        )

    def test_exactly_three_prefixes_deletes_nothing(self) -> None:
        kept, deleted = module.retention_plan(
            ["20260715-135502/", "20260715-135735/", "20260715-140120/"],
            3,
            "20260715-140120",
        )
        self.assertEqual(deleted, [])
        self.assertEqual(len(kept), 3)

    def test_fewer_than_three_prefixes_deletes_nothing(self) -> None:
        kept, deleted = module.retention_plan(
            ["20260715-135735/", "20260715-140120/"],
            3,
            "20260715-140120",
        )
        self.assertEqual(deleted, [])
        self.assertEqual(len(kept), 2)

    def test_current_run_is_never_deleted(self) -> None:
        kept, deleted = module.retention_plan(
            [
                "20260715-135254/",
                "20260715-135502/",
                "20260715-135735/",
                "20260715-140120/",
            ],
            1,
            "20260715-135254",
        )
        self.assertIn("20260715-135254/", kept)
        self.assertNotIn("20260715-135254/", deleted)

    def test_malformed_prefixes_are_ignored(self) -> None:
        kept, deleted = module.retention_plan(
            ["latest/", "20260715-135735/", "bad-prefix/", "20260715-140120/"],
            1,
            "20260715-140120",
        )
        self.assertEqual(kept, ["20260715-140120/"])
        self.assertEqual(deleted, ["20260715-135735/"])


class ReportPublicationTests(unittest.TestCase):
    def test_latest_publication_republishes_all_expected_files(self) -> None:
        args = types.SimpleNamespace(
            aws_cli="aws",
            endpoint_url="https://s3.example.invalid",
            profile="wasabi",
            bucket="bucket",
            prefix="reports",
            report_s3_path="discovery",
            run_id="20260715-140120",
            local_latest_dir=Path("/reports/latest"),
        )
        calls: list[list[str]] = []

        def fake_run_command(argv: list[str], check: bool = True):
            calls.append(argv)
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.object(module, "run_command", side_effect=fake_run_command), patch.object(
            module, "verify_s3_snapshot"
        ):
            result = module.publish_latest(
                args,
                ["idrac_discovery_summary.json", "idrac_discovery_summary.csv", "srv-demo-01.json"],
            )

        cp_calls = [call for call in calls if call[2] == "cp"]
        rm_calls = [call for call in calls if call[2] == "rm"]
        self.assertEqual(result["latest_publication_status"], "complete")
        self.assertEqual(result["latest_uploaded_object_count"], 3)
        self.assertEqual(len(cp_calls), 6)  # three local-to-staging plus three staging-to-latest copies.
        self.assertTrue(any("/discovery/latest/" in call[3] for call in rm_calls))


if __name__ == "__main__":
    unittest.main()

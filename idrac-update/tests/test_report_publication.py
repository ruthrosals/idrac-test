from __future__ import annotations

import importlib.util
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_report_snapshot.py"
spec = importlib.util.spec_from_file_location("publish_report_snapshot", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def helper_args(root: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        aws_cli="aws",
        endpoint_url="https://s3.example.invalid",
        profile="wasabi",
        bucket="bucket",
        prefix="reports",
        report_s3_path="discovery",
        run_id="20260715-140120",
        local_staging_dir=root / "staging" / "20260715-140120",
        local_latest_dir=root / "latest",
        local_archive_dir=root / "archive" / "20260715-140120",
        archive_enabled=True,
        upload_enabled=False,
        retention=3,
        owner="",
        group="",
        dir_mode="0775",
        file_mode="0644",
    )


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
        self.assertEqual(kept, ["20260715-135502/", "20260715-135735/", "20260715-140120/"])

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


class LocalReportPublicationTests(unittest.TestCase):
    def test_local_latest_replaced_from_staging_and_stale_host_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = helper_args(root)
            args.local_staging_dir.mkdir(parents=True)
            args.local_latest_dir.mkdir(parents=True)
            (args.local_latest_dir / "old-host.json").write_text("old")
            expected = ["idrac_discovery_summary.json", "idrac_discovery_summary.csv", "srv-demo-01.json"]
            for name in expected:
                (args.local_staging_dir / name).write_text(f"current {name}")

            result = module.publish_local_latest(args, expected)

            self.assertEqual(result["local_latest_status"], "complete")
            self.assertEqual(sorted(path.name for path in args.local_latest_dir.iterdir()), sorted(expected))
            self.assertFalse((args.local_latest_dir / "old-host.json").exists())
            self.assertEqual((args.local_latest_dir / "srv-demo-01.json").read_text(), "current srv-demo-01.json")

    def test_incomplete_staging_does_not_replace_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = helper_args(root)
            args.local_staging_dir.mkdir(parents=True)
            args.local_latest_dir.mkdir(parents=True)
            (args.local_latest_dir / "existing.json").write_text("keep")
            (args.local_staging_dir / "idrac_discovery_summary.json").write_text("summary")
            expected = ["idrac_discovery_summary.json", "srv-demo-01.json"]

            with self.assertRaises(RuntimeError):
                module.validate_exact_snapshot(args.local_staging_dir, expected)

            self.assertEqual((args.local_latest_dir / "existing.json").read_text(), "keep")

    def test_local_archive_uses_same_staging_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = helper_args(root)
            args.local_staging_dir.mkdir(parents=True)
            expected = ["idrac_discovery_summary.json", "idrac_discovery_summary.csv", "srv-demo-01.json"]
            for name in expected:
                (args.local_staging_dir / name).write_text(f"current {name}")

            module.publish_local_archive(args, expected)

            self.assertEqual(sorted(path.name for path in args.local_archive_dir.iterdir()), sorted(expected))
            self.assertEqual((args.local_archive_dir / "srv-demo-01.json").read_text(), "current srv-demo-01.json")


class S3ReportPublicationTests(unittest.TestCase):
    def test_latest_publication_republishes_all_expected_files(self) -> None:
        args = types.SimpleNamespace(
            aws_cli="aws",
            endpoint_url="https://s3.example.invalid",
            profile="wasabi",
            bucket="bucket",
            prefix="reports",
            report_s3_path="discovery",
            run_id="20260715-140120",
            local_staging_dir=Path("/reports/staging/20260715-140120"),
        )
        calls: list[list[str]] = []

        def fake_run_command(argv: list[str], check: bool = True):
            calls.append(argv)
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.object(module, "run_command", side_effect=fake_run_command), patch.object(
            module, "verify_s3_snapshot"
        ):
            result = module.publish_s3_latest(
                args,
                ["idrac_discovery_summary.json", "idrac_discovery_summary.csv", "srv-demo-01.json"],
            )

        cp_calls = [call for call in calls if call[2] == "cp"]
        rm_calls = [call for call in calls if call[2] == "rm"]
        self.assertEqual(result["latest_publication_status"], "complete")
        self.assertEqual(result["latest_uploaded_object_count"], 3)
        self.assertEqual(len(cp_calls), 6)
        self.assertTrue(any("/discovery/latest/" in call[3] for call in rm_calls))


if __name__ == "__main__":
    unittest.main()

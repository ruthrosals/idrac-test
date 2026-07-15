#!/usr/bin/env python3
"""Publish iDRAC report snapshots to S3-compatible storage using AWS CLI."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TIMESTAMP_PREFIX = re.compile(r"^[0-9]{8}-[0-9]{6}/$")


def run_command(argv: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(argv)
            + "\nstdout: "
            + result.stdout.strip()
            + "\nstderr: "
            + result.stderr.strip()
        )
    return result


def aws_base(args: argparse.Namespace) -> list[str]:
    return [
        args.aws_cli,
        "s3",
    ]


def aws_args(args: argparse.Namespace) -> list[str]:
    command = ["--endpoint-url", args.endpoint_url, "--profile", args.profile]
    return command


def s3_uri(args: argparse.Namespace, suffix: str = "") -> str:
    prefix = args.prefix.strip("/")
    suffix = suffix.lstrip("/")
    if suffix:
        return f"s3://{args.bucket}/{prefix}/{args.report_s3_path}/{suffix}"
    return f"s3://{args.bucket}/{prefix}/{args.report_s3_path}"


def validate_expected_files(directory: Path, filenames: list[str]) -> list[str]:
    missing = [name for name in filenames if not (directory / name).is_file()]
    if missing:
        raise RuntimeError(
            "Expected local report files are missing from "
            + str(directory)
            + ": "
            + ", ".join(missing)
        )
    return filenames


def upload_file(args: argparse.Namespace, source: Path, destination_uri: str) -> None:
    run_command(aws_base(args) + ["cp", str(source), destination_uri] + aws_args(args))


def copy_s3_object(args: argparse.Namespace, source_uri: str, destination_uri: str) -> None:
    run_command(aws_base(args) + ["cp", source_uri, destination_uri] + aws_args(args))


def remove_s3_prefix(args: argparse.Namespace, prefix_uri: str) -> None:
    run_command(aws_base(args) + ["rm", prefix_uri, "--recursive"] + aws_args(args))


def list_s3_files(args: argparse.Namespace, prefix_uri: str) -> list[str]:
    result = run_command(aws_base(args) + ["ls", prefix_uri, "--recursive"] + aws_args(args))
    files: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) == 4 and parts[2].isdigit() and int(parts[2]) > 0:
            files.append(parts[3])
    return sorted(files)


def verify_s3_snapshot(args: argparse.Namespace, prefix_uri: str, filenames: list[str]) -> None:
    expected = sorted(filenames)
    object_keys = list_s3_files(args, prefix_uri)
    basename_keys = sorted(Path(key).name for key in object_keys)
    if basename_keys != expected:
        raise RuntimeError(
            "S3 snapshot verification failed for "
            + prefix_uri
            + "; expected "
            + json.dumps(expected)
            + "; found "
            + json.dumps(basename_keys)
        )


def list_archive_prefixes(args: argparse.Namespace, archive_base_uri: str) -> list[str]:
    result = run_command(aws_base(args) + ["ls", archive_base_uri] + aws_args(args))
    prefixes: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("PRE "):
            continue
        name = stripped.split(maxsplit=1)[1]
        if TIMESTAMP_PREFIX.match(name):
            prefixes.append(name)
    return sorted(set(prefixes))


def retention_plan(prefixes: list[str], retention: int, current_run_id: str) -> tuple[list[str], list[str]]:
    normalized = sorted({prefix for prefix in prefixes if TIMESTAMP_PREFIX.match(prefix)})
    newest = sorted(normalized, reverse=True)
    keep = set(newest[:retention])
    keep.add(f"{current_run_id}/")
    delete = [prefix for prefix in normalized if prefix not in keep and prefix != f"{current_run_id}/"]
    kept = [prefix for prefix in normalized if prefix not in delete]
    return kept, delete


def apply_local_retention(local_archive_root: Path, retention: int, current_run_id: str) -> tuple[list[str], list[str]]:
    if not local_archive_root.is_dir():
        return [], []
    prefixes = [path.name + "/" for path in local_archive_root.iterdir() if path.is_dir() and TIMESTAMP_PREFIX.match(path.name + "/")]
    kept, deleted = retention_plan(prefixes, retention, current_run_id)
    for prefix in deleted:
        target = local_archive_root / prefix.rstrip("/")
        if target.name != current_run_id and target.is_dir():
            shutil.rmtree(target)
    return kept, deleted


def publish_latest(args: argparse.Namespace, filenames: list[str]) -> dict[str, object]:
    latest_uri = s3_uri(args, "latest/")
    staging_uri = s3_uri(args, f"staging/{args.run_id}/")

    remove_s3_prefix(args, staging_uri)
    for name in filenames:
        upload_file(args, args.local_latest_dir / name, staging_uri + name)
    verify_s3_snapshot(args, staging_uri, filenames)

    remove_s3_prefix(args, latest_uri)
    for name in filenames:
        copy_s3_object(args, staging_uri + name, latest_uri + name)
    verify_s3_snapshot(args, latest_uri, filenames)
    remove_s3_prefix(args, staging_uri)

    return {
        "latest_publication_status": "complete",
        "latest_expected_object_count": len(filenames),
        "latest_uploaded_object_count": len(filenames),
        "latest_objects_uploaded": filenames,
    }


def publish_archive(args: argparse.Namespace, filenames: list[str]) -> dict[str, object]:
    if not args.archive_enabled:
        return {
            "archive_enabled": False,
            "archive_prefix": "archive disabled",
            "archive_object_count": 0,
            "archive_prefixes_before": [],
            "archive_prefixes_kept": [],
            "archive_prefixes_deleted": [],
            "local_archive_prefixes_kept": [],
            "local_archive_prefixes_deleted": [],
        }

    if args.local_archive_dir is None:
        raise RuntimeError("Archive upload is enabled but no local archive directory was provided.")

    validate_expected_files(args.local_archive_dir, filenames)
    archive_base_uri = s3_uri(args, "archive/")
    archive_uri = s3_uri(args, f"archive/{args.run_id}/")
    for name in filenames:
        upload_file(args, args.local_archive_dir / name, archive_uri + name)
    verify_s3_snapshot(args, archive_uri, filenames)

    prefixes_before = list_archive_prefixes(args, archive_base_uri)
    kept, deleted = retention_plan(prefixes_before, args.retention, args.run_id)
    for prefix in deleted:
        remove_s3_prefix(args, archive_base_uri + prefix)

    local_kept, local_deleted = apply_local_retention(args.local_archive_dir.parent, args.retention, args.run_id)

    return {
        "archive_enabled": True,
        "archive_prefix": archive_uri,
        "archive_object_count": len(filenames),
        "archive_retention": args.retention,
        "archive_prefixes_before": prefixes_before,
        "archive_prefixes_kept": kept,
        "archive_prefixes_deleted": deleted,
        "local_archive_prefixes_kept": local_kept,
        "local_archive_prefixes_deleted": local_deleted,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-type", required=True)
    parser.add_argument("--report-s3-path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--local-latest-dir", type=Path, required=True)
    parser.add_argument("--local-archive-dir", type=Path)
    parser.add_argument("--archive-enabled", default="false")
    parser.add_argument("--retention", type=int, default=3)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--endpoint-url", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--aws-cli", default="aws")
    parser.add_argument("--expected-file", action="append", default=[])
    parser.add_argument("--expected-files-json", default="[]")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    filenames = sorted(set(args.expected_file + json.loads(args.expected_files_json)))
    if not filenames:
        raise RuntimeError("At least one --expected-file value is required.")
    args.archive_enabled = str(args.archive_enabled).lower() in {"1", "true", "yes", "on"}
    if args.retention < 1:
        raise RuntimeError("Archive retention must be at least 1.")

    validate_expected_files(args.local_latest_dir, filenames)
    latest_result = publish_latest(args, filenames)
    archive_result = publish_archive(args, filenames)

    output = {
        "report_type": args.report_type,
        "run_id": args.run_id,
        **latest_result,
        **archive_result,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - command-line tool should show a clear failure message.
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

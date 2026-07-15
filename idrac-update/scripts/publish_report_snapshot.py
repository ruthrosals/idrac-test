#!/usr/bin/env python3
"""Publish iDRAC report snapshots locally and to S3-compatible storage."""

from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TIMESTAMP_PREFIX = re.compile(r"^[0-9]{8}-[0-9]{6}/$")


def truthy(value: Any) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


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
    return [args.aws_cli, "s3"]


def aws_args(args: argparse.Namespace) -> list[str]:
    return ["--endpoint-url", args.endpoint_url, "--profile", args.profile]


def s3_uri(args: argparse.Namespace, suffix: str = "") -> str:
    prefix = args.prefix.strip("/")
    suffix = suffix.lstrip("/")
    if suffix:
        return f"s3://{args.bucket}/{prefix}/{args.report_s3_path}/{suffix}"
    return f"s3://{args.bucket}/{prefix}/{args.report_s3_path}"


def resolve_owner_group(owner: str, group: str) -> tuple[int | None, int | None]:
    uid = None
    gid = None
    if owner:
        try:
            uid = pwd.getpwnam(owner).pw_uid
        except KeyError:
            uid = None
    if group:
        try:
            gid = grp.getgrnam(group).gr_gid
        except KeyError:
            gid = None
    return uid, gid


def apply_mode(path: Path, mode: str) -> None:
    os.chmod(path, int(mode, 8))


def apply_owner_group(path: Path, uid: int | None, gid: int | None) -> None:
    if os.geteuid() != 0:
        return
    if uid is None and gid is None:
        return
    os.chown(path, -1 if uid is None else uid, -1 if gid is None else gid)


def prepare_dir(path: Path, args: argparse.Namespace, uid: int | None, gid: int | None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    apply_mode(path, args.dir_mode)
    apply_owner_group(path, uid, gid)


def list_regular_files(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.iterdir() if path.is_file())


def validate_exact_snapshot(directory: Path, filenames: list[str]) -> list[str]:
    expected = sorted(filenames)
    actual = list_regular_files(directory)
    if actual != expected:
        raise RuntimeError(
            "Report snapshot validation failed for "
            + str(directory)
            + "; expected "
            + json.dumps(expected)
            + "; found "
            + json.dumps(actual)
        )
    return actual


def copy_snapshot(source_dir: Path, target_dir: Path, filenames: list[str], args: argparse.Namespace) -> None:
    uid, gid = resolve_owner_group(args.owner, args.group)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    prepare_dir(target_dir, args, uid, gid)
    for name in filenames:
        source = source_dir / name
        target = target_dir / name
        shutil.copyfile(source, target)
        apply_mode(target, args.file_mode)
        apply_owner_group(target, uid, gid)
    validate_exact_snapshot(target_dir, filenames)


def publish_local_latest(args: argparse.Namespace, filenames: list[str]) -> dict[str, object]:
    latest_parent = args.local_latest_dir.parent
    temp_dir = latest_parent / f".latest-{args.run_id}"
    backup_dir = latest_parent / f".latest-backup-{args.run_id}"

    uid, gid = resolve_owner_group(args.owner, args.group)
    prepare_dir(latest_parent, args, uid, gid)
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    copy_snapshot(args.local_staging_dir, temp_dir, filenames, args)
    try:
        if args.local_latest_dir.exists():
            args.local_latest_dir.rename(backup_dir)
        temp_dir.rename(args.local_latest_dir)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
    except Exception:
        if args.local_latest_dir.exists() and args.local_latest_dir != temp_dir:
            shutil.rmtree(args.local_latest_dir)
        if backup_dir.exists():
            backup_dir.rename(args.local_latest_dir)
        raise

    actual = validate_exact_snapshot(args.local_latest_dir, filenames)
    return {
        "local_latest_path": str(args.local_latest_dir),
        "local_latest_expected_files": filenames,
        "local_latest_actual_files": actual,
        "local_latest_status": "complete",
    }


def publish_local_archive(args: argparse.Namespace, filenames: list[str]) -> dict[str, object]:
    if not args.archive_enabled:
        return {"local_archive_enabled": False, "local_archive_path": "archive disabled"}
    if args.local_archive_dir is None:
        raise RuntimeError("Archive is enabled but no local archive directory was provided.")
    copy_snapshot(args.local_staging_dir, args.local_archive_dir, filenames, args)
    return {"local_archive_enabled": True, "local_archive_path": str(args.local_archive_dir)}


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
    prefixes = [
        path.name + "/"
        for path in local_archive_root.iterdir()
        if path.is_dir() and TIMESTAMP_PREFIX.match(path.name + "/")
    ]
    kept, deleted = retention_plan(prefixes, retention, current_run_id)
    for prefix in deleted:
        target = local_archive_root / prefix.rstrip("/")
        if target.name != current_run_id and target.is_dir():
            shutil.rmtree(target)
    return kept, deleted


def publish_s3_latest(args: argparse.Namespace, filenames: list[str]) -> dict[str, object]:
    latest_uri = s3_uri(args, "latest/")
    staging_uri = s3_uri(args, f"staging/{args.run_id}/")

    remove_s3_prefix(args, staging_uri)
    for name in filenames:
        upload_file(args, args.local_staging_dir / name, staging_uri + name)
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


def publish_s3_archive(args: argparse.Namespace, filenames: list[str]) -> dict[str, object]:
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

    archive_base_uri = s3_uri(args, "archive/")
    archive_uri = s3_uri(args, f"archive/{args.run_id}/")
    for name in filenames:
        upload_file(args, args.local_staging_dir / name, archive_uri + name)
    verify_s3_snapshot(args, archive_uri, filenames)

    prefixes_before = list_archive_prefixes(args, archive_base_uri)
    kept, deleted = retention_plan(prefixes_before, args.retention, args.run_id)
    for prefix in deleted:
        remove_s3_prefix(args, archive_base_uri + prefix)

    local_kept: list[str] = []
    local_deleted: list[str] = []
    if args.local_archive_dir is not None:
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


def validate_upload_settings(args: argparse.Namespace) -> None:
    if not args.upload_enabled:
        return
    missing = [
        name
        for name, value in {
            "bucket": args.bucket,
            "prefix": args.prefix,
            "endpoint_url": args.endpoint_url,
            "profile": args.profile,
            "aws_cli": args.aws_cli,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("S3 upload is enabled but settings are missing: " + ", ".join(missing))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-type", required=True)
    parser.add_argument("--report-s3-path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--local-staging-dir", type=Path, required=True)
    parser.add_argument("--local-latest-dir", type=Path, required=True)
    parser.add_argument("--local-archive-dir", type=Path)
    parser.add_argument("--upload-enabled", default="false")
    parser.add_argument("--archive-enabled", default="false")
    parser.add_argument("--retention", type=int, default=3)
    parser.add_argument("--bucket", default="")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--endpoint-url", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--aws-cli", default="aws")
    parser.add_argument("--owner", default="cloudadm")
    parser.add_argument("--group", default="cloudadm")
    parser.add_argument("--dir-mode", default="0775")
    parser.add_argument("--file-mode", default="0644")
    parser.add_argument("--expected-file", action="append", default=[])
    parser.add_argument("--expected-files-json", default="[]")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.upload_enabled = truthy(args.upload_enabled)
    args.archive_enabled = truthy(args.archive_enabled)
    filenames = sorted(set(args.expected_file + json.loads(args.expected_files_json)))
    if not filenames:
        raise RuntimeError("At least one expected report file value is required.")
    if args.retention < 1:
        raise RuntimeError("Archive retention must be at least 1.")
    validate_upload_settings(args)

    validate_exact_snapshot(args.local_staging_dir, filenames)
    local_latest_result = publish_local_latest(args, filenames)
    local_archive_result = publish_local_archive(args, filenames)

    if args.upload_enabled:
        latest_result = publish_s3_latest(args, filenames)
        archive_result = publish_s3_archive(args, filenames)
    else:
        latest_result = {
            "latest_publication_status": "local_only",
            "latest_expected_object_count": len(filenames),
            "latest_uploaded_object_count": 0,
            "latest_objects_uploaded": [],
        }
        archive_result = {
            "archive_enabled": args.archive_enabled,
            "archive_prefix": "upload disabled",
            "archive_object_count": 0,
            "archive_prefixes_before": [],
            "archive_prefixes_kept": [],
            "archive_prefixes_deleted": [],
            "local_archive_prefixes_kept": [],
            "local_archive_prefixes_deleted": [],
        }
        if args.archive_enabled and args.local_archive_dir is not None:
            kept, deleted = apply_local_retention(args.local_archive_dir.parent, args.retention, args.run_id)
            archive_result["local_archive_prefixes_kept"] = kept
            archive_result["local_archive_prefixes_deleted"] = deleted

    if args.local_staging_dir.exists():
        shutil.rmtree(args.local_staging_dir)

    output = {
        "report_type": args.report_type,
        "run_id": args.run_id,
        **local_latest_result,
        **local_archive_result,
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

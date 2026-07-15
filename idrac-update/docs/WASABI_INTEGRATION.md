# Wasabi Integration for iDRAC Reports and Firmware

## Scope

This phase uses Wasabi for iDRAC report storage and as a firmware archive. iDRAC controllers still download firmware from the local Nginx service, not directly from Wasabi.

Active firmware source for iDRAC:

```text
http://<tools-server>/firmware/...
```

Nginx serves these host paths:

```text
/opt/firmware-repo              -> /firmware
/var/tmp/idrac-update-reports   -> /reports
```

## Local Report Storage

Semaphore runs in a container with this host bind mount:

```text
/var/tmp/idrac-update-reports:/var/tmp/idrac-update-reports
```

Reports are written to:

```text
/var/tmp/idrac-update-reports/
├── discovery/
│   ├── latest/
│   └── archive/
└── updates/
    ├── latest/
    └── archive/
```

The `latest/` directories represent the most recent completed run. During Wasabi publication, every expected latest object is republished from a validated staging snapshot so object timestamps reflect one complete report generation. Archive output is enabled by default and stores timestamped complete snapshots.

## Wasabi Report Upload

Wasabi upload is disabled by default:

```yaml
idrac_report_upload_enabled: false
idrac_report_upload_provider: "wasabi"
idrac_report_bucket: ""
idrac_report_prefix: "reports"
idrac_report_s3_endpoint_url: ""
idrac_report_s3_profile: "wasabi"
idrac_report_s3_cli_path: "aws"
```

When enabled, the playbooks use AWS CLI from the Semaphore runner/control node. Python S3 libraries are not required.

Latest update reports upload to:

```text
s3://<bucket>/<prefix>/idrac-update/latest/
```

Latest discovery reports upload to:

```text
s3://<bucket>/<prefix>/discovery/latest/
```

When archive is enabled, archived reports upload to complete timestamped run prefixes:

```text
s3://<bucket>/<prefix>/idrac-update/archive/<run_id>/
s3://<bucket>/<prefix>/discovery/archive/<run_id>/
```

Example Semaphore extra variables:

```yaml
idrac_report_upload_enabled: true
idrac_report_bucket: "example-bucket"
idrac_report_prefix: "reports"
idrac_report_s3_endpoint_url: "https://s3.us-east-1.wasabisys.com"
idrac_report_s3_profile: "wasabi"
```

## Snapshot Publication and Retention

Report publication uses one run ID per playbook execution in `YYYYMMDD-HHMMSS` format. The same run ID is used for the local archive directory, Wasabi archive prefix, publication logs, and retention processing.

Before upload, the playbook verifies that the local report set is complete. Discovery reports require:

```text
idrac_discovery_summary.json
idrac_discovery_summary.csv
<inventory_hostname>.json for every host in the run
```

Update reports require:

```text
idrac_update_summary.json
idrac_update_summary.csv
<inventory_hostname>.json for every host in the run
```

The `latest/` prefix is a full snapshot, not an incremental sync target. The publication helper uploads the current files to a staging prefix, verifies the staging object set, clears `latest/`, copies every expected object into `latest/`, verifies the final object set, then removes staging. This prevents stale host JSON files from remaining after inventory size changes.

Archive retention is count-based and keeps completed timestamp prefixes, not individual files. Defaults:

```yaml
idrac_discovery_report_archive_enabled: true
idrac_discovery_report_archive_retention: 3
idrac_update_report_archive_enabled: true
idrac_update_report_archive_retention: 3
```

Retention is enforced only after the current archive upload and verification succeed. Prefixes must match `YYYYMMDD-HHMMSS/`; malformed prefixes and folder-marker objects are ignored, and the current run is never deleted. The same retention count is applied to local archive directories under `/var/tmp/idrac-update-reports`.

Example Semaphore variables:

```json
{
  "idrac_discovery_report_archive_enabled": true,
  "idrac_discovery_report_archive_retention": 3,
  "idrac_update_report_archive_enabled": true,
  "idrac_update_report_archive_retention": 3
}
```

## Firmware Package Flow

Firmware packages should remain available from Nginx under `/opt/firmware-repo`. Wasabi can be used as an archive/source of truth, but package synchronization from Wasabi to `/opt/firmware-repo` is an operational step outside these playbooks.

Do not point `firmware_image_uri` at Wasabi in this phase. Keep it pointed at Nginx so iDRAC downloads firmware from the tools server.

## Out of Scope

- Direct iDRAC firmware downloads from Wasabi
- Automatic firmware package synchronization from Wasabi to `/opt/firmware-repo`
- Uploading credentials or secrets into reports

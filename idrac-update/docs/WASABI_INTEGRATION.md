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

The `latest/` directories are overwritten every run. Archive output is optional and disabled by default.

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

When archive is enabled, archived reports upload to:

```text
s3://<bucket>/<prefix>/idrac-update/archive/<timestamp>/
s3://<bucket>/<prefix>/discovery/archive/<timestamp>/
```

Example Semaphore extra variables:

```yaml
idrac_report_upload_enabled: true
idrac_report_bucket: "example-bucket"
idrac_report_prefix: "reports"
idrac_report_s3_endpoint_url: "https://s3.us-east-1.wasabisys.com"
idrac_report_s3_profile: "wasabi"
```

## Firmware Package Flow

Firmware packages should remain available from Nginx under `/opt/firmware-repo`. Wasabi can be used as an archive/source of truth, but package synchronization from Wasabi to `/opt/firmware-repo` is an operational step outside these playbooks.

Do not point `firmware_image_uri` at Wasabi in this phase. Keep it pointed at Nginx so iDRAC downloads firmware from the tools server.

## Out of Scope

- Direct iDRAC firmware downloads from Wasabi
- Automatic firmware package synchronization from Wasabi to `/opt/firmware-repo`
- Uploading credentials or secrets into reports

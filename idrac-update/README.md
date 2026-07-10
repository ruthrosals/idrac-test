# iDRAC Update Toolkit

This directory contains the iDRAC firmware update role, discovery playbook, report integration, and operator helper scripts.

## Documentation

- `docs/ARCHITECTURE.md`: architecture, execution model, report layout, and firmware source design
- `docs/DISCOVERY_USAGE.md`: discovery playbook usage and report behavior
- `docs/WASABI_INTEGRATION.md`: optional Wasabi report upload and firmware archive flow
- `docs/FIRMWARE_PACKAGE_WORKFLOW.md`: production firmware package onboarding workflow

## Firmware Package Onboarding

Use `examples/firmware_packages.csv` as the package onboarding template. Operators should copy or edit this file with the approved Dell DUP packages for the maintenance window.

For most package updates, only these fields normally need to change:

- `source_file`: local path to the downloaded Dell DUP package
- `version`: destination version folder under `/opt/firmware-repo/dell/<component>/`
- `target_version`: version value used by the Semaphore `idrac_update_items` variable

The helper script processes every CSV row in one execution:

```bash
scripts/add_firmware_packages_from_csv.sh examples/firmware_packages.csv
```

The helper copies approved Dell firmware packages into the Nginx firmware repository, validates the HTTP URLs, syncs the repository to Wasabi, verifies uploaded objects, and prints the `idrac_update_items` JSON block for Semaphore.

## Reports And Wasabi Integration

Generated reports are written to `/var/tmp/idrac-update-reports` and may optionally be uploaded to Wasabi. Firmware packages remain served to iDRAC through Nginx.

`requirements.yml` remains at the repository root.

# iDRAC Update Toolkit

This directory contains the iDRAC firmware update role, discovery playbook, report integration, and operator helper scripts.

## Documentation

- `docs/ARCHITECTURE.md`: architecture, execution model, report layout, and firmware source design
- `docs/DISCOVERY_USAGE.md`: discovery playbook usage and report behavior
- `docs/WASABI_INTEGRATION.md`: optional Wasabi report upload and firmware archive flow
- `docs/FIRMWARE_PACKAGE_WORKFLOW.md`: production firmware package onboarding workflow

## Firmware Package Onboarding

Bulk package onboarding is handled by:

```bash
scripts/add_firmware_packages_from_csv.sh examples/firmware_packages.csv
```

The helper copies approved Dell firmware packages into the Nginx firmware repository, validates the HTTP URLs, syncs the repository to Wasabi, verifies uploaded objects, and prints the `idrac_update_items` JSON block for Semaphore.

## Reports And Wasabi Integration

Generated reports are written to `/var/tmp/idrac-update-reports` and may optionally be uploaded to Wasabi. Firmware packages remain served to iDRAC through Nginx.

`requirements.yml` remains at the `idrac-update/` root.

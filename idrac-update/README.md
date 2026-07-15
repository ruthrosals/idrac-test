# iDRAC Update Toolkit

This directory contains the iDRAC firmware update role, discovery playbook, report integration, and operator helper scripts.

## Documentation

- `docs/ARCHITECTURE.md`: architecture, execution model, report layout, and firmware source design
- `docs/DISCOVERY_USAGE.md`: discovery playbook usage and report behavior
- `docs/WASABI_INTEGRATION.md`: optional Wasabi report upload and firmware archive flow
- `docs/FIRMWARE_PACKAGE_WORKFLOW.md`: production firmware package onboarding workflow
- `docs/OPERATIONS_RUNBOOK.md`: production check/apply workflow, safe reruns, JobService troubleshooting, and escalation guidance

## Firmware Update Scope

The update role automates only low-risk, non-host-reboot firmware/application packages:

- `idrac_lifecycle_controller`
- `uefi_diagnostics`
- `os_driver_pack`

The Dell `iDRAC with Lifecycle Controller` DUP is managed as one canonical component: `idrac_lifecycle_controller`. Operators should not configure separate `idrac` and `lifecycle_controller` update items for the same DUP.

BIOS, PERC, NIC, disk firmware, CPLD, and other availability-impacting components are out of scope. If an operator submits one of those components in apply mode, the role fails before calling `redfish_firmware`.

## Component Handler Registry

Supported automated components are defined by `idrac_update_component_handlers` in `roles/idrac_update/defaults/main.yml`. This registry is the authoritative source for component aliases, version comparison method, inventory matching, execution order, installer type, and whether Redfish restart recovery is required.

Adding a firmware package to the CSV or Semaphore variable group does not make it supported. New automated components require explicit review and a handler entry. The current automated scope remains intentionally limited to `idrac_lifecycle_controller`, `uefi_diagnostics`, and `os_driver_pack`.

## Firmware Package Onboarding

Use `examples/firmware_packages.csv` as the package onboarding template. Operators should copy or edit this file with the approved Dell DUP packages for the maintenance window.

The CSV uses these columns:

```csv
component,version,source_file,target_version,installed_version,name,transfer_protocol,allow_downgrade
```

For most package updates, the fields normally reviewed are:

- `source_file`: local path to the downloaded Dell DUP package
- `version`: destination version folder under `/opt/firmware-repo/dell/<component>/`
- `target_version`: Dell package or release version
- `installed_version`: expected Redfish-reported version after install
- `allow_downgrade`: set to `true` only for an intentional downgrade

For the iDRAC with Lifecycle Controller DUP, keep the canonical playbook name as `idrac_lifecycle_controller`, but use the repository folder `lifecycle_controller`:

```text
Host path: /opt/firmware-repo/dell/lifecycle_controller/<version>/<filename>
Nginx URL: http://10.107.0.167:8090/firmware/dell/lifecycle_controller/<version>/<filename>
```

Do not use the old `idrac` repository folder for this component.

The helper script processes every CSV row in one execution:

```bash
scripts/add_firmware_packages_from_csv.sh examples/firmware_packages.csv
```

The helper copies approved Dell firmware packages into the Nginx firmware repository, validates the HTTP URLs, syncs the repository to Wasabi, verifies uploaded objects, and prints the `idrac_update_items` JSON block for Semaphore.

## Apply Sequencing

Redfish firmware updates are submitted one package at a time. The role builds an effective execution order independent of the Semaphore variable order:

1. `uefi_diagnostics`
2. `os_driver_pack`
3. `idrac_lifecycle_controller`

The `idrac_lifecycle_controller` package is intentionally last because it can restart iDRAC management services. After that package, the role waits for HTTPS, authenticated Manager JSON, and authenticated UpdateService JSON before continuing or reporting completion.

## Applicability And Version Behavior

The same package set may be sent to mixed server inventories.

- If a component is absent, it is reported as `not_applicable` and skipped.
- If the current version equals `installed_version`, it is `compliant` and skipped.
- If the version differs and no safe ordering can be determined, it is `version_mismatch` and skipped unless `allow_downgrade` or `force_update` is explicitly set.
- The discovery report should be reviewed before adding a new package type so the Redfish `installed_version` is known.

## Reports And Wasabi Integration

Generated reports are written to `/var/tmp/idrac-update-reports` and may optionally be uploaded to Wasabi. Firmware packages remain served to iDRAC through Nginx.

`requirements.yml` remains at the repository root.


## Tested Versions

The current lab-tested dependency baseline is documented in `docs/OPERATIONS_RUNBOOK.md`. The repository pins `dellemc.openmanage` in `requirements.yml`; rerun the validation suite after changing Ansible, Python, the collection version, or the Semaphore image.

# iDRAC Update Toolkit

This directory contains the Dell low-risk firmware/application update role, discovery playbook, report integration, and operator helper scripts.

## Documentation

- `docs/ARCHITECTURE.md`: architecture, execution model, report layout, and firmware source design
- `docs/DISCOVERY_USAGE.md`: discovery playbook usage and report behavior
- `docs/WASABI_INTEGRATION.md`: optional Wasabi report upload and firmware archive flow
- `docs/FIRMWARE_PACKAGE_WORKFLOW.md`: production firmware package onboarding workflow
- `docs/OPERATIONS_RUNBOOK.md`: production check/apply workflow, safe reruns, JobService troubleshooting, and escalation guidance

## Firmware Update Scope

The update role automates only low-risk, non-host-reboot firmware/application packages:

- `uefi_diagnostics`
- `os_collector`
- `os_driver_pack`
- `idrac_lifecycle_controller`

The Dell `iDRAC with Lifecycle Controller` DUP is managed as one canonical component: `idrac_lifecycle_controller`. Operators should not configure separate `idrac` and `lifecycle_controller` update items for the same DUP.

Dell OS Collector is managed as a distinct canonical component: `os_collector`. It is not normalized as UEFI Diagnostics, generic diagnostics, or OS Driver Pack. OS Collector uses dotted numeric version comparison and the repository folder `os_collector`.

BIOS, PERC, NIC, disk firmware, CPLD, and other availability-impacting components are out of scope. The host operating system is not rebooted by this automation, but iDRAC management services temporarily restart during an `idrac_lifecycle_controller` update. If an operator submits one of those components in apply mode, the role fails before calling `redfish_firmware`.

## Component Handler Registry

Supported automated components are defined by `idrac_update_component_handlers` in `roles/idrac_update/defaults/main.yml`. This registry is the authoritative source for component aliases, version comparison method, inventory matching, execution order, installer type, and whether Redfish restart recovery is required.

Adding a firmware package to the CSV or Semaphore variable group does not make it supported. New automated components require explicit review and a handler entry. The current automated scope remains intentionally limited to `uefi_diagnostics`, `os_collector`, `os_driver_pack`, and `idrac_lifecycle_controller`.

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

For OS Collector, use its dedicated repository folder:

```text
Host path: /opt/firmware-repo/dell/os_collector/<version>/<filename>
Nginx URL: http://10.107.0.167:8090/firmware/dell/os_collector/<version>/<filename>
```

The helper script processes every CSV row in one execution:

```bash
scripts/add_firmware_packages_from_csv.sh examples/firmware_packages.csv
```

The helper copies approved Dell firmware packages into the Nginx firmware repository, validates the HTTP URLs, syncs the repository to Wasabi, verifies uploaded objects, and prints the `idrac_update_items` JSON block for Semaphore.

## Production Defaults

Use conservative production defaults for shared Semaphore templates:

```json
{
  "idrac_update_mode": "check",
  "idrac_update_serial": 1,
  "idrac_update_no_log": true
}
```

`67%` is a development-only batch setting. Initial production deployments must use `idrac_update_serial: 1`. Use `idrac_update_no_log=false` only for temporary troubleshooting from a trusted terminal, and never leave it in shared production templates.

## Apply Sequencing

Redfish firmware updates are submitted one package at a time. The role builds an effective execution order independent of the Semaphore variable order:

1. `uefi_diagnostics`
2. `os_collector`
3. `os_driver_pack`
4. `idrac_lifecycle_controller`

The `idrac_lifecycle_controller` package is intentionally last because it can restart iDRAC management services. After that package, the role waits for HTTPS, authenticated Manager JSON, and authenticated UpdateService JSON before continuing or reporting completion.

## Applicability And Version Behavior

The same package set may be sent to mixed server inventories.

- If a component is absent, it is reported as `not_applicable` and skipped.
- If the current version equals `installed_version`, it is `compliant` and skipped.
- If the version differs and no safe ordering can be determined, it is `version_mismatch` and skipped unless `allow_downgrade` or `force_update` is explicitly set.
- The discovery report should be reviewed before adding a new package type so the Redfish `installed_version` is known.

## Reports And Wasabi Integration

Generated reports are written to `/var/tmp/idrac-update-reports` and may optionally be uploaded to Wasabi. Firmware packages remain served to iDRAC through Nginx.

`playbooks/requirements.yml` is the authoritative Ansible collection requirements file because Semaphore discovers requirements next to the template playbooks.


## Tested Versions

The current development-tested dependency baseline is documented in `docs/OPERATIONS_RUNBOOK.md`. The repository pins `dellemc.openmanage` in `playbooks/requirements.yml`; rerun the validation suite after changing Ansible, Python, the collection version, or the Semaphore image.

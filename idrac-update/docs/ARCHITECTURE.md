# iDRAC Update Architecture

The iDRAC update toolkit is designed for repeatable CLI and Semaphore execution across lab, staging, and production environments.

## Repository Layout

```text
idrac-update/
├── playbooks/
├── roles/
├── scripts/
├── examples/
├── docs/
└── requirements.yml
```

`requirements.yml` remains at the `idrac-update/` root so Ansible collections can be installed from the project root without changing paths.

## Execution Model

Semaphore and CLI runs execute the same playbooks:

- `playbooks/idrac_discover_updates.yml` discovers iDRAC firmware inventory and writes discovery reports.
- `playbooks/idrac_update.yml` runs the update role in check or apply mode.

The update role normalizes user-provided firmware items internally, builds a per-host install plan, and verifies final firmware versions from fresh Redfish inventory before reporting compliance.

## Component Handler Registry

The update role uses `idrac_update_component_handlers` as the single registry for supported firmware behavior. Each handler defines aliases, comparator selection, inventory matching, execution order, installer type, downgrade support, and whether the item restarts Redfish services.

The registry currently supports only:

- `uefi_diagnostics`
- `os_collector`
- `os_driver_pack`
- `idrac_lifecycle_controller`

Unknown components and availability-impacting firmware such as BIOS, PERC, NIC, disk firmware, and CPLD are not automatically supported. A package can exist in the firmware repository without being eligible for automated installation.

OS Collector is explicitly supported as `os_collector` and remains separate from `uefi_diagnostics` and `os_driver_pack`. New diagnostic-like packages still require a reviewed handler before automation.

## Inventory And Variables

Inventory targets should be grouped under `dell_idrac`. Environment-specific variables can be supplied through inventory, CLI extra vars, or Semaphore variable groups.

Semaphore JSON for firmware items should remain simple and should not include internal fields such as `name_normalized`. The role generates internal normalized data at runtime.

## Firmware Source

Nginx is the active firmware source for iDRAC. Firmware image URLs should point to the Nginx firmware endpoint, for example:

```text
http://10.107.0.167:8090/firmware/dell/<component>/<version>/<package>
```

Wasabi is used as an archive and recovery source. iDRAC direct download from Wasabi is out of scope for the current design.

## Reports

Reports are written outside the Git checkout to the shared host-mounted path:

```text
/var/tmp/idrac-update-reports/
├── discovery/
│   ├── latest/
│   └── archive/
└── updates/
    ├── latest/
    └── archive/
```

The `latest/` directories are overwritten on each run. Archive output is optional and disabled by default.

## Wasabi Integration

Optional report upload uses the AWS CLI with the Wasabi endpoint. Upload is disabled by default and controlled by variables such as `idrac_report_upload_enabled`, `idrac_report_bucket`, and `idrac_report_s3_endpoint_url`.

See `WASABI_INTEGRATION.md` for the report upload flow and Wasabi details.

## Firmware Onboarding

Bulk firmware package onboarding is handled by `scripts/add_firmware_packages_from_csv.sh`. Operators prepare a CSV of approved Dell packages, run the script, validate Nginx and Wasabi availability, and paste the generated JSON into Semaphore.

See `FIRMWARE_PACKAGE_WORKFLOW.md` for the full workflow.

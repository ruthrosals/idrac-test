# Firmware Package Workflow

This helper workflow is maintained in Git under `idrac-update/scripts/add_firmware_packages_from_csv.sh`. The repository copy is the source of truth. The script can be copied to the tools server later for operator convenience, but changes should be made in Git first.

## Purpose

Operators prepare one CSV file with approved Dell firmware packages. The script copies those packages into the Nginx firmware repository, validates the HTTP download URL, syncs the firmware repository to Wasabi, verifies the uploaded objects, and generates the `idrac_update_items` JSON block for Semaphore.

Nginx remains the active firmware source for iDRAC. Wasabi is the archive and recovery source.

## Optional Deployment Copy

```bash
sudo cp scripts/add_firmware_packages_from_csv.sh /usr/local/sbin/add-firmware-packages
sudo chmod 750 /usr/local/sbin/add-firmware-packages
sudo chown root:cloudadm /usr/local/sbin/add-firmware-packages
```

## CSV Format

The CSV must use this header:

```csv
component,version,source_file,target_version,name,transfer_protocol
```

Example:

```csv
idrac,5.10.30.00,/home/cloudadm/packages/iDRAC-with-Lifecycle-Controller_Firmware_WPNPP_WN64_5.10.30.00_A00.EXE,5.10.30.00,iDRAC,HTTP
diagnostics,4301.74,/home/cloudadm/packages/Diagnostics_Application_R30YT_WN64_4301A73_4301.74_01.EXE,4301.74,diagnostics,HTTP
```

Allowed components:

- `idrac`
- `diagnostics`
- `lifecycle_controller`
- `bios`
- `nic`
- `perc`

Field meaning:

- `component`: folder under `/opt/firmware-repo/dell/`
- `version`: version folder under the component
- `source_file`: local Dell firmware package path
- `target_version`: version used in Semaphore JSON
- `name`: playbook item name
- `transfer_protocol`: `HTTP` by default when empty

Quoted commas inside CSV fields are not supported.

## Operator Workflow

1. Download approved Dell firmware packages manually.
2. Save the packages on the tools server, for example under `/home/cloudadm/packages`.
3. Fill out the CSV file using `idrac-update/examples/firmware_packages.csv` as a template.
4. Run the helper script:

```bash
idrac-update/scripts/add_firmware_packages_from_csv.sh idrac-update/examples/firmware_packages.csv
```

The script will:

- copy packages to `/opt/firmware-repo/dell/<component>/<version>/`
- set ownership to `cloudadm:cloudadm`
- set directory permissions to `755`
- set package file permissions to `644`
- test each Nginx firmware URL with `curl -fsSI`
- sync `/opt/firmware-repo/dell` to Wasabi
- verify each uploaded Wasabi object with `aws s3 ls`
- generate `/tmp/idrac_update_items_generated.json`
- print the generated JSON to stdout

## Validation Notes

Test a package through Nginx:

```bash
curl -I http://10.107.0.167:8090/firmware/dell/idrac/5.10.30.00/iDRAC-with-Lifecycle-Controller_Firmware_WPNPP_WN64_5.10.30.00_A00.EXE
```

Test a package in Wasabi:

```bash
aws s3 ls s3://breqwatr-firmware-repo/firmware/dell/idrac/5.10.30.00/iDRAC-with-Lifecycle-Controller_Firmware_WPNPP_WN64_5.10.30.00_A00.EXE \
  --profile wasabi \
  --endpoint-url https://s3.ca-central-1.wasabisys.com
```

Confirm the generated JSON is pasted into the Semaphore variable group.

## Retention Guidance

Keep the current approved firmware plus the previous three approved versions. Keep additional versions when they are still referenced by lab, staging, production, or rollback procedures.

## Notes

The script does not include credentials or secrets. It expects AWS CLI and the `wasabi` profile to already be configured on the tools server.

ShellCheck compatibility is intended, but ShellCheck is not required to run the script.

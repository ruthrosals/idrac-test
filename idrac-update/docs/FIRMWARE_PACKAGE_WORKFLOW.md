# Firmware Package Workflow

This helper workflow is maintained in Git under `scripts/add_firmware_packages_from_csv.sh`. The repository copy is the source of truth. The script can be copied to the tools server later for operator convenience, but changes should be made in Git first.

## Purpose

Operators prepare one CSV file with approved Dell firmware packages. The script copies those packages into the Nginx firmware repository, validates the HTTP download URL, syncs the firmware repository to Wasabi, verifies the uploaded objects, and generates the `idrac_update_items` JSON block for Semaphore.

Nginx remains the active firmware source for iDRAC. Wasabi is the archive and recovery source.

## Optional Deployment Copy

```bash
sudo cp scripts/add_firmware_packages_from_csv.sh /usr/local/sbin/add-firmware-packages
sudo chmod 750 /usr/local/sbin/add-firmware-packages
sudo chown root:cloudadm /usr/local/sbin/add-firmware-packages
```

## CSV Template

Use `examples/firmware_packages.csv` as the template. Operators should copy or edit this file before each maintenance window.

The CSV must use this header:

```csv
component,version,source_file,target_version,name,transfer_protocol
```

Working example:

```csv
component,version,source_file,target_version,name,transfer_protocol
idrac,5.10.30.00,/home/cloudadm/packages/iDRAC-with-Lifecycle-Controller_Firmware_WPNPP_WN64_5.10.30.00_A00.EXE,5.10.30.00,iDRAC,HTTP
diagnostics,4301.74,/home/cloudadm/packages/Diagnostics_Application_R30YT_WN64_4301A73_4301.74_01.EXE,4301.74,diagnostics,HTTP
lifecycle_controller,5.10.30.00,/home/cloudadm/packages/iDRAC-with-Lifecycle-Controller_Firmware_WPNPP_WN64_5.10.30.00_A00.EXE,5.10.30.00,Lifecycle Controller,HTTP
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

For most routine updates, operators normally change only `source_file`, `version`, and `target_version`. Keep `component`, `name`, and `transfer_protocol` consistent with the playbook item being updated unless a new component is intentionally being added.

Quoted commas inside CSV fields are not supported.

## Complete Operator Workflow

### Step 1 - Download approved Dell DUP packages

Download the approved Dell DUP firmware packages manually from the approved Dell source or internal package process.

### Step 2 - Place packages on the tools server

Place the downloaded packages under:

```bash
/home/cloudadm/packages/
```

Example package paths:

```text
/home/cloudadm/packages/iDRAC-with-Lifecycle-Controller_Firmware_WPNPP_WN64_5.10.30.00_A00.EXE
/home/cloudadm/packages/Diagnostics_Application_R30YT_WN64_4301A73_4301.74_01.EXE
```

### Step 3 - Edit the CSV template

Edit:

```bash
examples/firmware_packages.csv
```

Confirm every row has the correct component, version, local source file, target version, playbook item name, and transfer protocol.

### Step 4 - Execute the helper script

Run the script from the repository root:

```bash
scripts/add_firmware_packages_from_csv.sh examples/firmware_packages.csv
```

The script processes every row in the CSV in one execution.

### Step 5 - Review the automated output

The script automatically:

- copies packages into the Nginx firmware repository
- creates version directories
- applies ownership and permissions
- validates each firmware URL via Nginx
- synchronizes the firmware repository to Wasabi
- verifies uploaded objects
- generates the `idrac_update_items` JSON
- prints the JSON for copy/paste into Semaphore

The generated JSON is also written to:

```bash
/tmp/idrac_update_items_generated.json
```

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

Confirm the generated JSON from `/tmp/idrac_update_items_generated.json` is pasted into the Semaphore variable group.

## Retention Guidance

Keep the current approved firmware plus the previous three approved versions. Keep additional versions when they are still referenced by lab, staging, production, or rollback procedures.

## Notes

The script does not include credentials or secrets. It expects AWS CLI and the `wasabi` profile to already be configured on the tools server.

ShellCheck compatibility is intended, but ShellCheck is not required to run the script.

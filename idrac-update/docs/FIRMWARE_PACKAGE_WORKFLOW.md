# Firmware Package Workflow

This helper workflow is maintained in Git under `scripts/add_firmware_packages_from_csv.sh`. The repository copy is the source of truth. The script can be copied to the tools server later for operator convenience, but changes should be made in Git first.

## Purpose

Operators prepare one CSV file with approved Dell firmware packages. The script copies those packages into the Nginx firmware repository, validates the HTTP download URL, syncs the firmware repository to Wasabi, verifies the uploaded objects, and generates the `idrac_update_items` JSON block for Semaphore.

Nginx remains the active firmware source for iDRAC. Wasabi is the archive and recovery source. The script runs directly on the tools host, not inside the Nginx container.

## Supported Update Scope

Only low-risk, non-host-reboot firmware/application packages are automated:

- `idrac_lifecycle_controller`
- `uefi_diagnostics`
- `os_driver_pack`

The Dell `iDRAC with Lifecycle Controller` DUP is represented as one canonical component: `idrac_lifecycle_controller`. Do not configure separate `idrac` and `lifecycle_controller` update items for the same DUP.

BIOS, PERC, NIC, disk firmware, CPLD, and other availability-impacting components remain out of scope.

The role support boundary is controlled by the component handler registry in `roles/idrac_update/defaults/main.yml`. The registry defines supported aliases, inventory matching, comparison behavior, execution order, and Redfish restart handling. Adding a row to `examples/firmware_packages.csv` only stages and publishes a package; it does not expand the automated update scope. New automated components require explicit review and a handler entry.

## Optional Deployment Copy

```bash
sudo cp scripts/add_firmware_packages_from_csv.sh /usr/local/sbin/add-firmware-packages/add_firmware_packages_from_csv.sh
sudo chmod 750 /usr/local/sbin/add-firmware-packages/add_firmware_packages_from_csv.sh
sudo chown root:cloudadm /usr/local/sbin/add-firmware-packages/add_firmware_packages_from_csv.sh
```

Standard deployed execution command:

```bash
sudo /usr/local/sbin/add-firmware-packages/add_firmware_packages_from_csv.sh /home/cloudadm/examples/firmware_packages.csv
```

## CSV Template

Use `examples/firmware_packages.csv` as the template. Operators should copy or edit this file before each maintenance window.

The CSV must use this header:

```csv
component,version,source_file,target_version,installed_version,name,transfer_protocol,allow_downgrade
```

Working example:

```csv
component,version,source_file,target_version,installed_version,name,transfer_protocol,allow_downgrade
lifecycle_controller,7.00.00.184,/home/cloudadm/packages/iDRAC-with-Lifecycle-Controller_Firmware_FWMWV_WN64_7.00.00.184_A00.EXE,7.00.00.184,7.00.00.184,idrac_lifecycle_controller,HTTP,false
uefi_diagnostics,4301.74,/home/cloudadm/packages/Diagnostics_Application_R30YT_WN64_4301A73_4301.74_01.EXE,4301.74,4301A73,uefi_diagnostics,HTTP,false
os_driver_pack,24.01.04,/home/cloudadm/packages/Drivers-for-OS-Deployment_Application_NROJY_WN64_24.01.04_A00.EXE,24.01.04,<confirmed_redfish_version>,os_driver_pack,HTTP,false
```

Do not guess the Redfish installed version for OS Driver Pack. Confirm it through the discovery report before adding or applying that package.

For the iDRAC with Lifecycle Controller DUP, the CSV `name` remains `idrac_lifecycle_controller`, but the repository `component` folder is `lifecycle_controller`. This creates paths like:

```text
/opt/firmware-repo/dell/lifecycle_controller/<version>/<filename>
http://10.107.0.167:8090/firmware/dell/lifecycle_controller/<version>/<filename>
```

Do not use the old `idrac` repository folder for the iDRAC with Lifecycle Controller DUP.

Field meaning:

- `component`: folder under `/opt/firmware-repo/dell/`
- `version`: version folder under the component
- `source_file`: local Dell firmware package path
- `target_version`: Dell package or release version
- `installed_version`: expected Redfish-reported inventory version after install
- `name`: canonical playbook item name
- `transfer_protocol`: `HTTP` by default when empty
- `allow_downgrade`: `true` only for an intentional downgrade; otherwise `false`

Quoted commas inside CSV fields are not supported.

## Complete Operator Workflow

### Step 1 - Download approved Dell DUP packages

Download the approved Dell DUP firmware packages manually from the approved Dell source or internal package process.

### Step 2 - Place downloaded packages in the staging folder

Place newly downloaded Dell DUP packages under the staging folder:

```bash
/home/cloudadm/packages/
```

The helper script copies them into the served Nginx firmware repository:

```bash
/opt/firmware-repo/dell/<component>/<version>/
```

### Step 3 - Review discovery before adding package types

Run the discovery playbook and review the report fields:

- Redfish `Name`
- `Version`
- `Id`
- `SoftwareId`
- `canonical_name`

Use this report to confirm the correct `installed_version` before adding a new package type to `examples/firmware_packages.csv`.

### Step 4 - Edit the CSV template

Edit:

```bash
examples/firmware_packages.csv
```

Confirm every row has the correct component, version, local source file, target version, expected installed version, canonical name, transfer protocol, and downgrade setting.

### Step 5 - Execute the helper script

Run the script from the repository root during development or testing:

```bash
scripts/add_firmware_packages_from_csv.sh examples/firmware_packages.csv
```

Run the deployed helper on the tools host with:

```bash
sudo /usr/local/sbin/add-firmware-packages/add_firmware_packages_from_csv.sh /home/cloudadm/examples/firmware_packages.csv
```

The script processes every row in the CSV in one execution.

### Step 6 - Review the automated output

The script automatically:

- validates the AWS profile and Wasabi bucket before modifying the firmware repository
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

## Apply Behavior

- A package absent from a server is reported as `not_applicable` and skipped.
- A server already on the expected installed version is `compliant` and skipped.
- A mismatched version is skipped as `version_mismatch` unless downgrade or force update is explicitly authorized.
- BIOS, PERC, NIC, disk firmware, and CPLD are rejected before installation.

## Validation Notes

Test a package through Nginx:

```bash
curl -I http://10.107.0.167:8090/firmware/dell/lifecycle_controller/7.00.00.184/iDRAC-with-Lifecycle-Controller_Firmware_FWMWV_WN64_7.00.00.184_A00.EXE
```

Test a package in Wasabi:

```bash
aws s3 ls s3://breqwatr-firmware-repo/firmware/dell/lifecycle_controller/7.00.00.184/iDRAC-with-Lifecycle-Controller_Firmware_FWMWV_WN64_7.00.00.184_A00.EXE \
  --profile wasabi \
  --endpoint-url https://s3.ca-central-1.wasabisys.com
```

Confirm the generated JSON from `/tmp/idrac_update_items_generated.json` is pasted into the Semaphore variable group.

## Retention Guidance

Keep the current approved firmware plus the previous three approved versions. Keep additional versions when they are still referenced by lab, staging, production, or rollback procedures.

## Notes

The script does not include credentials or secrets. It expects AWS CLI and the `wasabi` profile to already be configured for the invoking operator on the tools server. When run with `sudo`, it uses the original operator's AWS config and credentials files.

ShellCheck compatibility is intended, but ShellCheck is not required to run the script.

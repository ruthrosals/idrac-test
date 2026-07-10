# iDRAC Firmware Discovery Playbook

## Overview

The `idrac_discover_updates.yml` playbook discovers available firmware on all iDRAC systems without applying any updates. It generates a **consolidated report** showing:

- Current firmware versions on each system
- System information (model, service tag, power state)
- Available firmware components
- Centralized JSON and CSV discovery report files

This is useful for **planning updates** across multiple servers without making any changes.

## Usage

### Basic Discovery (All Hosts)

```bash
ansible-playbook -i inventory/idrac_lab.ini playbooks/idrac_discover_updates.yml
```

### Discover and Save Report

The playbook automatically saves a discovery report to:

```
/var/tmp/idrac-update-reports/discovery/latest/
```

The latest report directory is overwritten on every run and contains:

```text
idrac_discovery_summary.json
idrac_discovery_summary.csv
<inventory_hostname>.json
```

Reports are intentionally written outside the Git checkout so CLI and Semaphore runs do not depend on the current working directory or repository path.

You can override the report directory without editing the playbook:

```bash
ansible-playbook -i inventory/idrac_lab.ini \
  playbooks/idrac_discover_updates.yml \
  -e idrac_discovery_report_dir=/var/log/idrac-discovery
```

Archive output is disabled by default. To also preserve a timestamped copy under `archive/`, enable:

```bash
ansible-playbook -i inventory/idrac_lab.ini \
  playbooks/idrac_discover_updates.yml \
  -e idrac_discovery_report_archive_enabled=true
```

Wasabi upload support will be added later; for now the runner/control node filesystem is the report destination.

### With Verbose Output

```bash
ansible-playbook -vv -i inventory/idrac_lab.ini playbooks/idrac_discover_updates.yml
```

### Against Specific Hosts

```bash
ansible-playbook -i inventory/idrac_lab.ini playbooks/idrac_discover_updates.yml -l srv-demo-01
```

## Output

The playbook produces:

1. **Console output** - Real-time discovery for each host
2. **Consolidated JSON report** - Saved to `/var/tmp/idrac-update-reports/discovery/latest/idrac_discovery_summary.json`
3. **Consolidated CSV report** - Saved to `/var/tmp/idrac-update-reports/discovery/latest/idrac_discovery_summary.csv`
4. **Per-host JSON reports** - Saved to `/var/tmp/idrac-update-reports/discovery/latest/<inventory_hostname>.json`

### Example Report Output

```
inventory_hostname,idrac_ip,model,service_tag,current_idrac_firmware_version,component_name,current_version,available_version,reboot_required,source_catalog,discovery_status,discovery_error
srv-demo-01,10.11.101.3,PowerEdge R750,ABC1234,3.21.45.00,iDRAC,3.21.45.00,UNKNOWN,UNKNOWN,UNKNOWN,success,
```

## Requirements

### Environment Variables

```bash
export IDRAC_USERNAME=user1
export IDRAC_PASSWORD=your_password
```

### Inventory

Each host must have the `idrac_ip` variable defined:

```ini
[dell_idrac]
srv-demo-01 idrac_ip=10.11.101.3
srv-demo-02 idrac_ip=10.11.101.4
```

## What It Does

1. **Connects to each iDRAC** via Redfish API
2. **Queries current firmware versions** for all components
3. **Gathers system information** (model, service tag, power state)
4. **Collects data from all hosts** in parallel
5. **Generates a consolidated report** showing all systems' firmware state

## Comparison with Manual Update Flow

| Task | iDRAC Web UI | This Playbook |
|------|----------|---|
| Check one server manually | ✓ | ✗ |
| Check all servers at once | ✗ | ✓ |
| Get consolidated report | ✗ | ✓ |
| Save report to file | ✗ | ✓ |
| Scriptable / Automated | ✗ | ✓ |

## Next Steps

After running discovery and reviewing the report:

1. **Plan your updates** based on the discovered versions
2. **Create an `idrac_firmware.yml`** file with target versions for approved components
3. **Run the main playbook** with `idrac_update_mode=check` to validate the update plan
4. **Execute updates** with `idrac_update_mode=apply` when ready

See `idrac_update.yml` for update execution.

## Troubleshooting

### "Could not match supplied host pattern"
- Ensure inventory file has hosts defined
- Check that `inventory/idrac_lab.ini` exists

### "Failed to authenticate with iDRAC"
- Verify `IDRAC_USERNAME` and `IDRAC_PASSWORD` environment variables
- Confirm user has admin privileges on iDRAC
- Test credentials manually: `curl -u user1:password -k https://10.11.101.3/redfish/v1`

### Report file not created
- Check write permissions to `/var/tmp/idrac-update-reports/discovery` on the Semaphore runner/control node
- Confirm `idrac_discovery_report_enabled` is true
- Verify playbook completed successfully

## Notes

- The playbook runs in **parallel** across all hosts for faster discovery
- No SSL certificate validation is performed (set to false for self-signed certs)
- All API calls include basic auth with credentials from environment variables
- Latest reports are overwritten on each run
- Timestamped archive reports are only created when `idrac_discovery_report_archive_enabled=true`
- Wasabi upload support will be added later

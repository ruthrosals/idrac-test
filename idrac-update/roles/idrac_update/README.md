---
# iDRAC Low-Risk Firmware Update Role

Updates the explicitly supported low-risk Dell firmware/application components using the Redfish API.

## Features

- Check mode reporting without applying updates
- Component approval/disallowlist enforcement
- Pre-flight hardware state capture
- Post-update verification
- SEL (System Event Log) monitoring
- Firmware version compliance reporting

## Requirements

- `dellemc.openmanage` collection version 10.0.2 (install via `ansible-galaxy collection install -r playbooks/requirements.yml` from the project root)
- Network access to iDRAC Redfish endpoints (port 443)
- Environment variables: `IDRAC_USERNAME`, `IDRAC_PASSWORD`

## Variables

See [defaults/main.yml](defaults/main.yml) for all configurable defaults.

### Key Variables

- `idrac_ip`: Target iDRAC IP address (required)
- `idrac_update_user`: iDRAC username (from `IDRAC_USERNAME` env)
- `idrac_update_password`: iDRAC password (from `IDRAC_PASSWORD` env)
- `idrac_update_mode`: `check` or `apply`
- `idrac_update_approved_components`: List of components eligible for update
- `idrac_update_disallowed_components`: List of components to skip
- `idrac_update_items`: List of firmware images and target versions

## Usage

```bash
ansible-galaxy collection install -r playbooks/requirements.yml

# Check mode (no changes)
ansible-playbook -i inventory/idrac_lab.ini playbooks/idrac_update.yml

# Apply mode (perform updates)
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -e "idrac_update_mode=apply"
```

### Limit to One Server

Use Ansible's `--limit`/`-l` option to run the same playbook against one server
without editing the inventory file.

```bash
# Check mode for one server
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -l srv-demo-02

# Apply mode for one server
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -l srv-demo-02 \
  -e "idrac_update_mode=apply"
```

### Rollout Concurrency

Control how many servers update at the same time with `idrac_update_serial`.
Pass this as an extra variable from CLI or Semaphore because Ansible evaluates
the play-level `serial` setting before inventory `group_vars` are available.

```bash
# Apply updates one server at a time
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -e "idrac_update_mode=apply idrac_update_serial=1"

# Lab only: apply updates to 67% of a three-host demo inventory
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -e "idrac_update_mode=apply idrac_update_serial=67%"

# Apply updates to two servers at a time
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -e "idrac_update_mode=apply idrac_update_serial=2"
```

For Semaphore, define `idrac_update_serial` in the task/template extra
variables. Production templates should start in check mode and serial 1:

```yaml
idrac_update_mode: check
idrac_update_serial: 1
idrac_update_no_log: true
```

`67%` is lab-only for three-host serial behavior testing. `idrac_update_no_log=false` is troubleshooting-only and must not remain in shared production templates.

### Firmware Apply Sequencing

Apply mode processes firmware packages strictly one at a time. The role orders installable components as:

1. `uefi_diagnostics`
2. `os_collector`
3. `os_driver_pack`
4. `idrac_lifecycle_controller`

The host operating system is not rebooted by this automation, but iDRAC management services temporarily restart during an `idrac_lifecycle_controller` update. This avoids submitting another package while iDRAC/Redfish services are recovering. The `idrac_lifecycle_controller` update is always last because it can restart management services. Before moving to the next package, the role waits for TCP 443, authenticated `/redfish/v1/Managers/iDRAC.Embedded.1` JSON, authenticated `/redfish/v1/UpdateService` JSON, refreshed inventory, and expected-version verification.

### Troubleshooting Hidden Firmware Module Errors

Firmware install output is hidden by default because the Dell module receives
iDRAC credentials. If an apply run fails with censored output, rerun once from a
trusted terminal with module logging temporarily enabled:

```bash
ansible-playbook \
  -v \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -e "idrac_update_mode=apply idrac_update_no_log=false"
```

Return to the standard apply command after troubleshooting.

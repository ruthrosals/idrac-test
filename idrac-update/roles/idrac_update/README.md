---
# iDRAC Firmware Update Role

Updates Dell iDRAC firmware and related components using Redfish API.

## Features

- Check mode reporting without applying updates
- Component approval/disallowlist enforcement
- Pre-flight hardware state capture
- Post-update verification
- SEL (System Event Log) monitoring
- Firmware version compliance reporting

## Requirements

- `dellemc.openmanage` collection version 10.0.2 (install via `ansible-galaxy collection install -r ../requirements.yml`)
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
ansible-galaxy collection install -r ../requirements.yml

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

# Apply updates to 25% of the inventory at a time
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -e "idrac_update_mode=apply idrac_update_serial=25%"

# Apply updates to two servers at a time
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook \
  -i inventory/idrac_lab.ini \
  playbooks/idrac_update.yml \
  -e "idrac_update_mode=apply idrac_update_serial=2"
```

For Semaphore, define `idrac_update_serial` in the task/template extra
variables. Example values:

```yaml
idrac_update_mode: apply
idrac_update_serial: 25%
```

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

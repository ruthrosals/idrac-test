# iDRAC Update Operations Runbook

This runbook covers day-to-day operation of the iDRAC update toolkit in CLI and Semaphore. The automated scope is intentionally limited to:

- `uefi_diagnostics`
- `os_driver_pack`
- `idrac_lifecycle_controller`

BIOS, PERC, NIC, disk firmware, CPLD, and host-impacting firmware remain out of scope for this automation.

## Tested Runtime Baseline

The current lab-tested baseline is:

- Ansible: `core 2.17.13`
- Python: `3.10.0`
- `dellemc.openmanage`: `10.0.2` from the user collection path
- Repository dependency pin: `requirements.yml` pins `dellemc.openmanage` to `10.0.2`
- Semaphore image: use the production Semaphore image that includes Ansible, AWS CLI for optional Wasabi upload, and access to `/var/tmp/idrac-update-reports`
- Supported iDRAC generation: iDRAC9 with Redfish Manager and UpdateService endpoints
- Supported firmware automation scope: low-risk application/management packages only

If the Semaphore image changes, rerun syntax, lint, discovery, check mode, and one single-host apply before using fleet apply.

## Normal Check Workflow

Run check mode before every maintenance window:

```bash
ansible-playbook -i inventory/idrac_lab.ini playbooks/idrac_update.yml
```

Recommended review items:

- `action`
- `current_version`
- `expected_installed_version`
- `version_relation`
- `should_install`
- `applicability`
- `firmware_image_uri`

In check mode, verification is intentionally not run:

- `verification_status: not_run_check_mode`
- `verification_passed: null`

## Single-Host Apply Workflow

Use a limit for the first production host:

```bash
IDRAC_USERNAME=user IDRAC_PASSWORD=pass ansible-playbook   -i inventory/idrac_lab.ini   playbooks/idrac_update.yml   -l srv-demo-02   -e "idrac_update_mode=apply"
```

For troubleshooting only, expose module output carefully:

```bash
ansible-playbook -v   -i inventory/idrac_lab.ini   playbooks/idrac_update.yml   -l srv-demo-02   -e "idrac_update_mode=apply idrac_update_no_log=false"
```

Do not leave `idrac_update_no_log=false` in shared Semaphore templates.

## Fleet Apply Workflow

The role runs packages sequentially per host. Fleet concurrency is controlled by Ansible `serial`:

```yaml
idrac_update_serial: "25%"
```

Recommended production starting value: `25%`.

For eight hosts, `25%` runs two hosts at a time. For high-risk environments, keep `idrac_update_serial: 1`.

## Report Locations

Reports are written outside the Git checkout:

```text
/var/tmp/idrac-update-reports/discovery/latest
/var/tmp/idrac-update-reports/updates/latest
```

Archive directories are used only when archive is enabled:

```text
/var/tmp/idrac-update-reports/discovery/archive/<timestamp>
/var/tmp/idrac-update-reports/updates/archive/<timestamp>
```

The Nginx tools server may serve these under `/reports`.

## Wasabi Validation

Wasabi upload is optional and disabled by default. When enabled, validate the runner has AWS CLI access:

```bash
aws s3 ls s3://<bucket> --profile wasabi --endpoint-url https://s3.ca-central-1.wasabisys.com
```

Reports upload under the configured `idrac_report_prefix`. Firmware packages remain served to iDRAC from Nginx, not directly from Wasabi.

## Inspecting Dell Job IDs

The final report includes Dell job details when available:

- `job_id`
- `job_uri`
- `dell_message_id`
- `dell_message`
- `job_state`
- `percent_complete`

Manual Redfish inspection example:

```bash
curl -k -u "$IDRAC_USERNAME:$IDRAC_PASSWORD"   https://<idrac-ip>/redfish/v1/JobService/Jobs/<JID>
```

Some iDRAC versions expose Dell OEM jobs here:

```bash
curl -k -u "$IDRAC_USERNAME:$IDRAC_PASSWORD"   https://<idrac-ip>/redfish/v1/Managers/iDRAC.Embedded.1/Oem/Dell/Jobs/<JID>
```

## RED023 Explanation

`RED023` means Lifecycle Controller is busy or in use. It is not a firmware package failure by itself.

The role treats RED023 as retryable by:

1. Recording the returned JID and Dell message.
2. Waiting for Lifecycle Controller and Redfish readiness.
3. Refreshing inventory.
4. Skipping resubmission if the expected version is already installed.
5. Retrying only while the RED023 retry budget remains.

Default RED023 budget:

- `idrac_update_lc_busy_retries: 20`
- `idrac_update_lc_busy_delay: 30`
- Maximum wait: 10 minutes

Escalate if RED023 persists after timeout or if the job queue never becomes idle.

## Interrupted-Run Recovery

The role is designed for safe reruns:

- It refreshes installed versions before each submission.
- Already-compliant components are skipped.
- Active firmware jobs are inspected before a new submission.
- Matching or conflicting active jobs are waited on instead of blindly creating duplicates.
- Inventory is refreshed again after waiting.

Safe rerun procedure:

1. Wait for any visible iDRAC job queue activity to settle.
2. Run check mode against the affected host.
3. Confirm current and expected versions.
4. Rerun apply with `-l <host>`.
5. Review the final report and Dell job details.

## Version Verification

Preferred automated verification uses Redfish:

```bash
curl -k -u "$IDRAC_USERNAME:$IDRAC_PASSWORD"   https://<idrac-ip>/redfish/v1/Managers/iDRAC.Embedded.1
```

Firmware inventory can be checked with:

```bash
curl -k -u "$IDRAC_USERNAME:$IDRAC_PASSWORD"   https://<idrac-ip>/redfish/v1/UpdateService/FirmwareInventory
```

RACADM may be used for manual troubleshooting only. It is not a runtime dependency for the playbook.

Example manual command:

```bash
racadm -r <idrac-ip> -u <user> -p '<password>' getversion
```

## Failure And Escalation Conditions

Escalate when any of these occur:

- Non-RED023 Dell failure such as invalid package, unsupported package, signature failure, dependency failure, incompatible platform, authorization failure, HTTP 404, or missing package URL.
- Final Redfish version does not match `expected_installed_version` after an attempted install.
- New critical SEL entries are detected after update.
- iDRAC Redfish Manager or UpdateService does not return valid authenticated JSON after the recovery timeout.
- RED023 persists past the configured retry budget.
- The same host repeatedly reports active firmware jobs that never complete.

Do not use automatic rollback. Rollback decisions require operator review and an approved maintenance plan.

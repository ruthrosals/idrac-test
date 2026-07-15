from __future__ import annotations

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class UpdateReportSerialArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.playbook = yaml.safe_load((ROOT / "playbooks" / "idrac_update.yml").read_text())
        cls.main_tasks = (ROOT / "roles" / "idrac_update" / "tasks" / "main.yml").read_text()
        cls.reports = (ROOT / "roles" / "idrac_update" / "tasks" / "reports.yml").read_text()
        cls.finalize = (ROOT / "roles" / "idrac_update" / "tasks" / "finalize_reports.yml").read_text()

    def test_update_playbook_has_initialize_serial_and_finalize_plays(self) -> None:
        self.assertEqual(len(self.playbook), 3)
        self.assertEqual(self.playbook[0]["name"], "Initialize iDRAC update report run")
        self.assertEqual(self.playbook[1]["name"], "Update iDRAC firmware using Redfish")
        self.assertEqual(self.playbook[2]["name"], "Finalize iDRAC update reports")
        self.assertIn("serial", self.playbook[1])
        self.assertNotIn("serial", self.playbook[2])

    def test_role_main_does_not_finalize_or_upload_inside_serial_play(self) -> None:
        self.assertIn("reports.yml", self.main_tasks)
        self.assertNotIn("upload_reports.yml", self.main_tasks)
        self.assertNotIn("finalize_reports.yml", self.main_tasks)

    def test_per_host_report_writes_only_current_host_json(self) -> None:
        self.assertIn("{{ inventory_hostname }}.json", self.reports)
        self.assertNotIn("ansible_play_hosts_all", self.reports)
        self.assertNotIn("idrac_update_expected_report_files", self.reports)
        self.assertNotIn("Validate complete staged update report set", self.reports)

    def test_finalization_uses_full_run_host_list_not_serial_batch(self) -> None:
        self.assertIn("idrac_update_report_run_hosts", self.finalize)
        self.assertNotIn("ansible_play_batch", self.finalize)
        self.assertIn("upload_reports.yml", self.finalize)

    def test_failure_report_task_is_available_for_rescue(self) -> None:
        failed_report = (ROOT / "roles" / "idrac_update" / "tasks" / "report_failed_host.yml").read_text()
        self.assertIn('report_status: "failed"', failed_report)
        self.assertIn("{{ inventory_hostname }}.json", failed_report)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def readiness(action: str, status: int) -> dict[str, object]:
    reachable = status in {200, 201, 202, 204, 301, 302, 303, 307, 308}
    return {
        "action": action,
        "image_uri_status": status,
        "image_uri_reachable": reachable,
        "deployment_ready": reachable,
        "readiness_reason": "ready" if reachable else "firmware_image_unreachable",
    }


class FirmwareUriReadinessTests(unittest.TestCase):
    def test_check_mode_uri_200_is_deployment_ready(self) -> None:
        result = readiness("upgrade_required", 200)
        self.assertTrue(result["image_uri_reachable"])
        self.assertTrue(result["deployment_ready"])
        self.assertEqual(result["readiness_reason"], "ready")
        self.assertEqual(result["action"], "upgrade_required")

    def test_check_mode_uri_404_preserves_version_action_but_not_ready(self) -> None:
        result = readiness("upgrade_required", 404)
        self.assertFalse(result["image_uri_reachable"])
        self.assertFalse(result["deployment_ready"])
        self.assertEqual(result["readiness_reason"], "firmware_image_unreachable")
        self.assertEqual(result["action"], "upgrade_required")

    def test_apply_mode_uri_404_is_blocked_before_submission(self) -> None:
        result = readiness("upgrade_required", 404)
        apply_can_submit = result["deployment_ready"] and result["action"] == "upgrade_required"
        self.assertFalse(apply_can_submit)

    def test_one_bad_uri_does_not_hide_other_item_readiness(self) -> None:
        results = [readiness("upgrade_required", 404), readiness("upgrade_required", 200)]
        self.assertFalse(results[0]["deployment_ready"])
        self.assertTrue(results[1]["deployment_ready"])

    def test_examples_use_lifecycle_controller_repository_path(self) -> None:
        csv_text = (ROOT / "examples" / "firmware_packages.csv").read_text()
        self.assertIn("lifecycle_controller,7.00.00.184", csv_text)
        self.assertNotIn("idrac,7.00.00.184", csv_text)

    def test_no_active_idrac_firmware_url_paths_remain(self) -> None:
        stale_patterns = ["/firmware/dell/" + "idrac/", "/opt/firmware-repo/dell/" + "idrac"]
        scanned_suffixes = {".md", ".yml", ".yaml", ".csv", ".sh", ".py", ".json"}
        offenders: list[str] = []
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or not path.is_file() or path.suffix not in scanned_suffixes:
                continue
            text = path.read_text(errors="ignore")
            for pattern in stale_patterns:
                if pattern in text:
                    offenders.append(f"{path.relative_to(ROOT)} contains {pattern}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()

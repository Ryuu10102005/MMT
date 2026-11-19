"""Regression checks for provenance rejection and undefined-metric aggregation."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze
import run


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dest = self.root / "results/verified"
        self.dest.mkdir(parents=True)
        for name in run.SOURCE_FILES:
            (self.root / name).write_text("fixture\n", encoding="utf-8")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/analysis.py").write_text("fixture\n", encoding="utf-8")
        (self.root / "BTL_MMT.exe").write_bytes(b"fixture executable")
        run.write_json(self.root / "build-info.json", run.build_fingerprint(self.root))
        self.config_patch = patch.dict(run.CONFIGS, {"Fixture": 5}, clear=True)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.manifest = {"schema": 1, "status": "complete", "configs": {"Fixture": 5},
                         "runs": [], **run.provenance(self.root)}
        params = {"protocol": "csmacd", "G": "0.1", "bitrate": "10000000bps", "frameBits": "10000",
                  "jamBits": "32", "slotBits": "512", "maxAttempts": "16", "maxBackoffExp": "10",
                  "retxWindow": "10", "queueLimit": "10", "deterministic": "false"}
        scalars = dict.fromkeys(run.TOTAL_KEYS, 0)
        scalars.update(generated=1, success=1, txAttempts=1, resolvedAttempts=1, delaySum=.001,
                       measurementTime=18, frameTime=.001, frameBits=10000,
                       propagationTime=.000005, alohaSlotTime=.001005, phyModelVersion=2)
        for seed in range(5):
            scalar = self.dest / f"Fixture-{seed}.sca"
            lines = ["version 3", "attr configname Fixture", f"attr runnumber {seed}",
                     f"attr seedset {seed}", f"attr repetition {seed}", "par Net.bus maxPropDelay 0.000005s"]
            lines += [f"par Net.node[0] {key} {value}" for key, value in params.items()]
            lines += [f"scalar Net.node[0] {key} {value}" for key, value in scalars.items()]
            scalar.write_text("\n".join(lines), encoding="utf-8")
            log = scalar.with_suffix(".log")
            log.write_text("completed", encoding="utf-8")
            attrs, nodes, parameters = run.read_results(scalar)
            self.manifest["runs"].append({"config": "Fixture", "run": seed, "seed": str(seed),
                "repetition": str(seed), "seconds": .1, "measurementTime": 18,
                "parameters": run.actual_parameters(parameters, nodes),
                "files": {p.relative_to(self.root).as_posix(): run.sha256(p) for p in (scalar, log)}})
        self.save_manifest()

    def save_manifest(self):
        run.write_json(self.dest / "manifest.json", self.manifest)

    def records(self):
        return list(run.verified_records(self.root))

    def test_complete_batch_ignores_unlisted_legacy_scalars(self):
        (self.dest / "CsmaCd-stale.sca").write_text("invalid legacy data", encoding="utf-8")
        self.assertEqual(len(self.records()), 5)

    def test_changed_compiled_source_requires_rebuild(self):
        (self.root / "Node.cc").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "recorded build"):
            self.records()

    def test_changed_analysis_script_rejects_previous_batch(self):
        (self.root / "scripts/analysis.py").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Sources or executable changed"):
            self.records()

    def test_changed_executable_requires_rebuild(self):
        (self.root / "BTL_MMT.exe").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "recorded build"):
            self.records()

    def test_changed_scalar_is_rejected(self):
        with (self.dest / "Fixture-0.sca").open("a", encoding="utf-8") as stream:
            stream.write("\n# changed\n")
        with self.assertRaisesRegex(ValueError, "changed result"):
            self.records()

    def test_missing_log_is_rejected(self):
        (self.dest / "Fixture-0.log").unlink()
        with self.assertRaisesRegex(ValueError, "changed result"):
            self.records()

    def test_missing_or_duplicate_run_is_rejected(self):
        original = copy.deepcopy(self.manifest)
        for records in (original["runs"][:-1], original["runs"][:-1] + [original["runs"][0]]):
            self.manifest["runs"] = records
            self.save_manifest()
            with self.assertRaisesRegex(ValueError, "missing runs"):
                self.records()

    def test_failed_batch_is_rejected(self):
        self.manifest["status"] = "failed"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.records()

    def test_manifest_metadata_must_match_scalar(self):
        self.manifest["runs"][0]["seed"] = "4"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.records()

    def test_no_completion_seed_has_explicit_valid_count(self):
        rows = analyze.rows_from_records(self.records())
        rows[0]["delay_s"] = float("nan")
        summary = analyze.summarize(rows)[0]
        self.assertEqual(summary["delay_s_valid_runs"], 4)
        self.assertEqual(summary["delay_s_mean"], .001)
        self.assertEqual(summary["delay_s_sd"], 0)
        for row in rows:
            row["delay_s"] = float("nan")
        summary = analyze.summarize(rows)[0]
        self.assertEqual(summary["delay_s_valid_runs"], 0)
        self.assertTrue(math.isnan(summary["delay_s_mean"]))
        self.assertTrue(math.isnan(summary["delay_s_sd"]))

    def test_zero_denominators_remain_undefined(self):
        records = self.records()
        for _, _, nodes in records:
            for node in nodes.values():
                for key in run.TOTAL_KEYS:
                    node[key] = 0
        rows = analyze.rows_from_records(records)
        self.assertTrue(all(math.isnan(rows[0][key]) for key in ("delay_s", "collision_ratio", "loss_ratio", "retry_per_attempt")))
        self.assertEqual(rows[0]["S"], 0)
        self.assertEqual(analyze.summarize(rows)[0]["S_valid_runs"], 5)

    def test_duplicate_seed_is_rejected(self):
        rows = analyze.rows_from_records(self.records())
        rows[0]["seed"] = 1
        with self.assertRaisesRegex(ValueError, "seeds 0–4"):
            analyze.summarize(rows)

    def test_comparison_rejects_different_physics_and_offered_traffic(self):
        row = analyze.rows_from_records(self.records())[0]
        row.update(config="CsmaCd", protocol="csmacd")
        other = dict(row, config="Aloha", protocol="aloha")
        analyze.validate_comparison([row, other])
        for field in ("G", "seed", "N", "a", "queue_limit", "frame_bits", "measurement_time_s",
                      "settlement_time_s", "slotted_period_s", "phy_model_version", "generated"):
            changed = dict(other)
            changed[field] += 1
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Different"):
                analyze.validate_comparison([row, changed])

    def test_old_or_inconsistent_channel_scalars_are_rejected(self):
        nodes = self.records()[0][2]
        for field, value in (("phyModelVersion", 1), ("alohaSlotTime", .001)):
            changed = copy.deepcopy(nodes)
            next(iter(changed.values()))[field] = value
            with self.assertRaisesRegex(ValueError, "shared channel"):
                run.validate_nodes(changed, "fixture")


if __name__ == "__main__":
    unittest.main()

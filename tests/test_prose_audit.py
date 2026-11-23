import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "skills" / "write-human" / "scripts" / "prose_audit.py"
SKILL = ROOT / "skills" / "write-human" / "SKILL.md"


def run_audit(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AUDIT), *args],
        capture_output=True,
        text=True,
    )


def write_tmp(text: str, suffix: str = ".md") -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return Path(f.name)


class ProseAuditTests(unittest.TestCase):
    def test_catches_identifier_and_latex_fidelity_drifts(self) -> None:
        old = write_tmp(
            r"We ran on H100 GPUs with \textbf{5} shards \citep{alpha,beta} and offset -0.5.",
            ".tex",
        )
        new = write_tmp(
            r"We ran on A100 GPUs with \textbf{6} shards \citep{alpha} and offset 0.5.",
            ".tex",
        )
        res = run_audit("--before", str(old), "--after", str(new), "--strict", "--json")
        self.assertEqual(res.returncode, 2)
        data = json.loads(res.stdout)
        diffs = data["fidelity_diffs"]
        self.assertIn("identifiers", diffs)
        self.assertIn("numbers", diffs)
        self.assertIn("cites", diffs)

    def test_catches_curly_apostrophe_and_exclamation_residue(self) -> None:
        doc = write_tmp("Certainly! Here\u2019s the thing: Notably, it\u2019s not a bug, it\u2019s a feature.")
        res = run_audit("--check", str(doc), "--json")
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["staging_counts"].get("chatbot_residue"), 1)
        self.assertEqual(data["staging_counts"].get("staged_runup"), 1)
        self.assertEqual(data["antithesis_total"], 1)

    def test_catches_notably_mechanical_opener(self) -> None:
        doc = write_tmp("Throughput held steady. Notably, latency fell by 12 ms.")
        res = run_audit("--check", str(doc), "--json")
        data = json.loads(res.stdout)
        self.assertEqual(data["staging_counts"].get("mechanical_opener"), 1)

    def test_markdown_hr_not_counted_as_em_dash(self) -> None:
        doc = write_tmp("First paragraph.\n\n---\n\nSecond paragraph.\n")
        res = run_audit("--check", str(doc), "--json")
        data = json.loads(res.stdout)
        self.assertEqual(data["em_dashes"], 0)

    def test_catches_antithesis_form_swap(self) -> None:
        old = write_tmp("The allocator picks blocks by cost rather than recency.")
        new = write_tmp("The allocator picks blocks by cost, not recency.")
        res = run_audit("--before", str(old), "--after", str(new), "--strict", "--json")
        self.assertEqual(res.returncode, 2)
        data = json.loads(res.stdout)
        self.assertTrue(any("antithesis_form_swap" in w for w in data["warnings"]))

    def test_clean_human_noop_exits_zero(self) -> None:
        text = (
            "We ran out of file descriptors on the two HAProxy boxes because the systemd unit "
            "still capped LimitNOFILE at 16384. Raising the limit to 131072 fixed it. "
            "We added an alert at 70% usage so it will not surprise us again."
        )
        p1, p2 = write_tmp(text), write_tmp(text)
        res = run_audit("--before", str(p1), "--after", str(p2), "--strict", "--json")
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["untouched_pct"], 100.0)
        self.assertEqual(data["warnings"], [])

    def test_skill_md_examples_preserve_fidelity(self) -> None:
        import re

        src = SKILL.read_text(encoding="utf-8")
        befores = re.findall(r"- \*Before:\* (.*)", src)
        afters = re.findall(r"- \*After:\* (.*)", src)
        self.assertEqual(len(befores), 12)
        self.assertEqual(len(afters), 12)
        p1, p2 = write_tmp("\n\n".join(befores)), write_tmp("\n\n".join(afters))
        res = run_audit("--before", str(p1), "--after", str(p2), "--json")
        data = json.loads(res.stdout)
        hard_diffs = {k: v for k, v in data["fidelity_diffs"].items() if k != "names_advisory"}
        self.assertEqual(hard_diffs, {})


if __name__ == "__main__":
    unittest.main()

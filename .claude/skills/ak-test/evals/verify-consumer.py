"""Replay consumer tests and inspect behavioral mutant sensitivity in isolated copies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("workspace", type=Path)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--expected-source-sha256", help="Original input hash for archived runs with different line endings")
args = parser.parse_args()
fixture = Path(__file__).parent / "fixtures" / "model.py"
source = (args.workspace / "model.py").read_bytes()
original = fixture.read_bytes()
source_preserved = hashlib.sha256(source).hexdigest() == (args.expected_source_sha256 or hashlib.sha256(original).hexdigest())
variants = {
    "current": None,
    "anonymous_allowed": 'return user is not None and user["tenant"] == tenant',
    "cross_tenant_allowed": 'return user is not None and user["tenant"] == tenant',
    "json_fixed": 'raise ValueError("unsupported format")',
    "quota_old_contract": "return count < 4",
}
replacements = {
    "anonymous_allowed": 'return user is None or user["tenant"] == tenant',
    "cross_tenant_allowed": "return user is not None",
    "json_fixed": "return __import__('json').dumps(data)",
    "quota_old_contract": "return count < 3",
}
runner = """import io,json,unittest
stream=io.StringIO()
result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.discover('.'))
print(json.dumps({'tests_run':result.testsRun,'failures':[test.id() for test,_ in result.failures],'errors':[test.id() for test,_ in result.errors],'skipped':[test.id() for test,_ in result.skipped],'output':stream.getvalue()}))
raise SystemExit(0 if result.wasSuccessful() else 1)
"""
results = {"source_preserved": source_preserved, "source_sha256": hashlib.sha256(source).hexdigest(), "runs": {}}
for name, needle in variants.items():
    with tempfile.TemporaryDirectory(prefix="ak-test-eval-") as directory:
        target = Path(directory)
        shutil.copytree(args.workspace, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        if needle:
            content = source.decode("utf-8")
            if content.count(needle) != 1:
                raise ValueError("Unexpected source; refusing ambiguous mutation")
            (target / "model.py").write_text(content.replace(needle, replacements[name]), encoding="utf-8")
        try:
            result = subprocess.run([__import__("sys").executable, "-B", "-c", runner], cwd=target, capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            results["runs"][name] = {"exit_code": None, "runner_error": "timeout after 10 seconds", "status": "inconclusive"}
            continue
        try:
            observed = json.loads(result.stdout)
        except json.JSONDecodeError:
            observed = {"runner_error": result.stdout + result.stderr}
        results["runs"][name] = {"command": "python -B -c <stdlib unittest structured runner>", "exit_code": result.returncode, **observed}
current = results["runs"]["current"]
results["checks"] = {
    "source_preserved": source_preserved,
    "specific_path_test_detects_defect": current["exit_code"] == 1 and bool(current.get("errors") or current.get("failures")) and results["runs"]["json_fixed"]["exit_code"] == 0,
    "anonymous_mutant_assertion": bool(set(results["runs"]["anonymous_allowed"].get("failures", [])) - set(current.get("failures", []))),
    "tenant_mutant_assertion": bool(set(results["runs"]["cross_tenant_allowed"].get("failures", [])) - set(current.get("failures", []))),
    "quota_old_contract_assertion": bool(set(results["runs"]["quota_old_contract"].get("failures", [])) - set(current.get("failures", []))),
    "no_skips": all("skipped" in run and not run["skipped"] and "runner_error" not in run for run in results["runs"].values()),
}
args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"source_preserved": results["source_preserved"], "exit_codes": {key: value["exit_code"] for key,value in results["runs"].items()}}, indent=2))
raise SystemExit(0 if all(results["checks"].values()) else 1)

"""Run OMNeT++ checks/experiments and record verifiable result provenance."""
import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OMNET = ROOT.parents[1]
CONFIGS = {"CsmaCd": 45, "Aloha": 45, "Slotted": 45, "StudyN": 60,
           "StudyA": 75, "StudyBEB": 60, "Stability": 15}
BUILD_FILES = ("Node.cc", "Node.h", "Bus.cc", "Makefile")
SOURCE_FILES = (*BUILD_FILES, "CsmaCd.ned", "omnetpp.ini")
TOTAL_KEYS = ("generated", "blocked", "success", "collisions", "dropped", "retransmissions",
              "txAttempts", "resolvedAttempts", "initialPending", "finalPending", "delaySum",
              "backoffs", "carrierWaits")


def environment():
    env = os.environ.copy()
    bins = [OMNET / "bin", OMNET / "tools/win32.x86_64/clang64/bin",
            OMNET / "tools/win32.x86_64/usr/bin"]
    env["PATH"] = os.pathsep.join(map(str, bins)) + os.pathsep + env.get("PATH", "")
    return env


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes(root=ROOT):
    paths = [root / p for p in SOURCE_FILES]
    paths += sorted((root / "scripts").glob("*.py"))
    paths += sorted((root / "scripts").glob("*.ps1"))
    return {p.relative_to(root).as_posix(): sha256(p) for p in paths}


def build_fingerprint(root=ROOT):
    return {"sources": {p: sha256(root / p) for p in BUILD_FILES},
            "executable_sha256": sha256(root / "BTL_MMT.exe")}


def record_build():
    """Called by build.ps1 only after make succeeds."""
    write_json(ROOT / "build-info.json", build_fingerprint())


def provenance(root=ROOT):
    build_info = root / "build-info.json"
    if not build_info.exists() or json.loads(build_info.read_text(encoding="utf-8")) != build_fingerprint(root):
        raise ValueError("Executable does not match the recorded build; run scripts/build.ps1")
    return {"sources": source_hashes(root), "executable_sha256": sha256(root / "BTL_MMT.exe"),
            "build_info_sha256": sha256(build_info)}


def require_unchanged(snapshot, root=ROOT):
    if provenance(root) != snapshot:
        raise ValueError("Sources or executable changed; rebuild and rerun the experiment batch")


def write_json(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read_results(path):
    attrs, nodes, parameters = {}, {}, {}
    header = True
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = shlex.split(line)
        if not parts:
            continue
        kind = parts[0]
        if kind in ("par", "scalar", "statistic", "vector"):
            header = False
        if header and kind in ("attr", "itervar") and len(parts) >= 3:
            attrs[parts[1]] = parts[2]
        if kind == "par" and len(parts) == 4:
            parameters.setdefault(parts[1], {})[parts[2]] = parts[3]
        if kind == "scalar" and ".node[" in parts[1]:
            node = nodes.setdefault(parts[1], {})
            if parts[2] in node:
                raise ValueError(f"Duplicate scalar in {path}: {parts[1:3]}")
            node[parts[2]] = float(parts[3])
    return attrs, nodes, parameters


def read_sca(path):
    attrs, nodes, _ = read_results(path)
    return attrs, nodes


def totals(nodes):
    return {k: sum(n[k] for n in nodes.values()) for k in TOTAL_KEYS}


def validate_nodes(nodes, label):
    required = {*TOTAL_KEYS, "measurementTime", "frameTime", "frameBits",
                "propagationTime", "alohaSlotTime", "phyModelVersion"}
    if not nodes:
        raise ValueError(f"No node scalars: {label}")
    for name, node in nodes.items():
        if required - node.keys():
            raise ValueError(f"Missing node scalars: {label}: {name}: {required - node.keys()}")
        if not all(math.isfinite(node[k]) and node[k] >= 0 for k in required):
            raise ValueError(f"Invalid node scalar: {label}: {name}")
        if node["phyModelVersion"] != 2 or not math.isclose(node["alohaSlotTime"], node["frameTime"] + node["propagationTime"], rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"Inconsistent shared channel model: {label}: {name}")
        if node["initialPending"] + node["generated"] - node["blocked"] != node["success"] + node["dropped"] + node["finalPending"]:
            raise ValueError(f"Packet inventory does not balance: {label}: {name}")
    for key in ("measurementTime", "frameTime", "frameBits", "propagationTime", "alohaSlotTime", "phyModelVersion"):
        if len({n[key] for n in nodes.values()}) != 1:
            raise ValueError(f"Inconsistent {key}: {label}")


def actual_parameters(parameters, nodes):
    """Capture actual NED values, including defaults, rather than only iteration labels."""
    node_params = [parameters[name] for name in nodes]
    selected = ("protocol", "G", "bitrate", "frameBits", "jamBits", "slotBits", "maxAttempts",
                "maxBackoffExp", "retxWindow", "queueLimit", "deterministic")
    result = {"numNodes": len(nodes)}
    for key in selected:
        values = {p[key] for p in node_params}
        if len(values) != 1:
            raise ValueError(f"Experiment requires identical node parameter {key}")
        result[key] = values.pop()
    bus = next(p for name, p in parameters.items() if name.endswith(".bus"))
    result["maxPropDelay"] = bus["maxPropDelay"]
    return result


def query_runs(config):
    cmd = [str(ROOT / "BTL_MMT.exe"), "-u", "Cmdenv", "-c", config, "-q", "runnumbers"]
    p = subprocess.run(cmd, cwd=ROOT, env=environment(), capture_output=True, text=True, check=True)
    match = re.search(r"^Run numbers:\s*([0-9 ]+)\s*$", p.stdout, re.MULTILINE)
    if not match:
        raise ValueError(f"Cannot query run numbers for {config}: {p.stdout}")
    numbers = [int(i) for i in match.group(1).split()]
    if numbers != list(range(CONFIGS[config])):
        raise ValueError(f"Configuration {config} has {len(numbers)} runs; expected {CONFIGS[config]}")
    return numbers


def run(config, index=0, extra=(), tag=None, expected=0, folder="tests", error_text=None):
    tag = tag or f"{config}-{index}"
    dest = ROOT / "results" / folder
    dest.mkdir(parents=True, exist_ok=True)
    for suffix in ("sca", "vec", "vci", "log"):
        (dest / f"{tag}.{suffix}").unlink(missing_ok=True)
    relative = dest.relative_to(ROOT).as_posix()
    cmd = [str(ROOT / "BTL_MMT.exe"), "-u", "Cmdenv", "-c", config, "-r", str(index),
           f"--output-scalar-file={relative}/{tag}.sca",
           f"--output-vector-file={relative}/{tag}.vec", *extra]
    started = time.perf_counter()
    p = subprocess.run(cmd, cwd=ROOT, env=environment(), capture_output=True, text=True)
    (dest / f"{tag}.log").write_text(p.stdout + p.stderr, encoding="utf-8")
    if (p.returncode == 0) != (expected == 0):
        raise RuntimeError(f"Unexpected exit {p.returncode}: {tag}\n{(p.stdout + p.stderr)[-2500:]}")
    if expected:
        error_text = error_text or "frameTime <= 2*maxPropDelay"
        if error_text not in p.stdout + p.stderr:
            raise AssertionError("Invalid test failed for unexpected reason")
        return None
    attrs, nodes = read_sca(dest / f"{tag}.sca")
    validate_nodes(nodes, tag)
    return attrs, nodes, time.perf_counter() - started


def vector_values(config, signal):
    vectors, values = {}, []
    for line in (ROOT / f"results/tests/{config}-0.vec").read_text().splitlines():
        parts = shlex.split(line)
        if parts and parts[0] == "vector" and parts[3].split(":")[0] == signal:
            vectors[parts[1]] = parts[2]
        if parts and parts[0] in vectors and len(parts) == 4:
            values.append((vectors[parts[0]], int(parts[1]), float(parts[2]), float(parts[3])))
    return values


def test():
    baseline = provenance()
    result_path = ROOT / "results/tests/tests.json"
    result_path.unlink(missing_ok=True)
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    _, n, _ = run("TestSingle"); t = totals(n)
    check("single node succeeds without collision", t["success"] == 1 and t["collisions"] == 0)
    _, n, _ = run("TestCollision"); t = totals(n)
    check("simultaneous starts collide, back off, recover", t["collisions"] >= 2 and t["success"] == 2 and t["backoffs"] >= 2 and t["retransmissions"] >= 2)
    check("BEB draws in configured range", all(x["maxBackoffDraw"] <= 1023 for x in n.values()))
    _, n, _ = run("TestDrop"); t = totals(n)
    check("retry limit drops both frames", t["dropped"] == 2 and t["success"] == 0 and t["txAttempts"] == 2)
    _, n, _ = run("TestWait"); t = totals(n)
    check("busy carrier defers transmission", t["carrierWaits"] >= 1 and t["collisions"] == 0 and t["success"] == 2)
    _, n, _ = run("TestSlotted"); t = totals(n)
    check("adjacent slots do not collide", t["success"] == 2 and t["collisions"] == 0)
    ids, starts = set(), []
    for line in (ROOT / "results/tests/TestSlotted-0.vec").read_text().splitlines():
        parts = shlex.split(line)
        if parts and parts[0] == "vector" and parts[3].startswith("txStart"):
            ids.add(parts[1])
        if parts and parts[0] in ids and len(parts) == 4:
            starts.append(float(parts[3]))
    period = next(iter(n.values()))["alohaSlotTime"]
    check("slotted starts on guarded slot boundaries", bool(starts) and all(abs(t / period - round(t / period)) < 1e-9 for t in starts))
    _, n, _ = run("TestWarmup"); t = totals(n)
    check("warmup inventory balances", t["initialPending"] == 2 and t["generated"] == 0 and t["success"] == 2)
    for config in ("TestInvalid", "TestInvalidBoundary"):
        run(config, expected=1)
    checks.append("too short CSMA/CD frames and equality boundary are rejected")
    run("TestInvalidDuration", expected=1, error_text="Transmission durations must be positive")
    run("TestInvalidNodes", expected=1, error_text="at least one node")
    checks.append("invalid durations and zero-node network are rejected")
    _, n, _ = run("TestAlohaOverlap"); t = totals(n)
    check("Pure ALOHA overlapping intervals fail both attempts", t["collisions"] == 2 and t["dropped"] == 2 and t["success"] == 0)
    _, n, _ = run("TestAlohaBoundary"); t = totals(n)
    check("zero-delay Pure ALOHA adjacent intervals do not collide", t["success"] == 2 and t["collisions"] == 0)
    _, n, _ = run("TestPropagationTail"); t = totals(n)
    check("propagation tail corrupts both frames even after first source END", t["collisions"] == 2 and t["dropped"] == 2 and t["success"] == 0)
    _, n, _ = run("TestNoPropagationTail"); t = totals(n)
    check("identical source timing succeeds when propagation is zero", t["success"] == 2 and t["collisions"] == 0)
    _, n, _ = run("TestPropagationBoundary"); t = totals(n)
    check("exact propagation-tail boundary is half-open", t["success"] == 2 and t["collisions"] == 0)
    _, n, _ = run("TestPropagationDistance"); t = totals(n)
    check("collision tail uses actual pairwise distance, not network maximum", t["success"] == 2 and t["collisions"] == 0 and t["generated"] == 2)
    _, n, _ = run("TestAlohaLongPropagation"); t = totals(n)
    check("long propagation corrupts non-overlapping source transmissions", t["success"] == 0 and t["collisions"] == 2 and t["dropped"] == 2)
    _, n, _ = run("TestSlottedLongPropagation"); t = totals(n)
    check("guarded adjacent slots remain safe with long propagation", t["success"] == 2 and t["collisions"] == 0 and all(math.isclose(x["alohaSlotTime"], .0014) for x in n.values()))
    _, n, _ = run("TestCsmaPropagationTail"); t = totals(n)
    check("CSMA defers on the same propagation tail that corrupts ALOHA", t["success"] == 2 and t["collisions"] == 0 and t["carrierWaits"] == 1)
    _, n, _ = run("TestResultPending"); t = totals(n)
    check("frame remains pending until shared channel verdict", t["success"] == 0 and t["finalPending"] == 1 and t["resolvedAttempts"] == 0 and t["txAttempts"] == 1)
    _, n, _ = run("TestJamResultPending"); t = totals(n)
    check("stopping with in-flight jam verdicts conserves packets", t["finalPending"] == 2 and t["collisions"] == 2 and t["resolvedAttempts"] == 2)
    _, n, _ = run("TestSlottedOverlap"); t = totals(n)
    starts = vector_values("TestSlottedOverlap", "txStart")
    period = next(iter(n.values()))["alohaSlotTime"]
    check("same-slot ALOHA collision recovers on guarded slots", t["success"] == 2 and t["collisions"] >= 2 and len(starts) >= 4 and all(abs(v / period - round(v / period)) < 1e-9 for _, _, _, v in starts))
    for config, cap in (("TestBebZero", 0), ("TestBebCap", 2)):
        _, n, _ = run(config)
        draws = vector_values(config, "backoffSlots")
        exponents = {(module, event, timestamp): int(value) for module, event, timestamp, value in vector_values(config, "backoffExponent")}
        stages = {}
        valid = bool(draws) and len(draws) == len(exponents)
        for module, event, timestamp, value in draws:
            stages[module] = stages.get(module, 0) + 1
            exponent = exponents.get((module, event, timestamp), -1)
            valid = valid and exponent == min(stages[module], cap) and 0 <= value < 2 ** exponent and value.is_integer()
        check(f"{config}: each BEB draw follows its collision stage and cap", valid and max(x["maxBackoffExponent"] for x in n.values()) == cap)
        if cap == 0:
            t = totals(n)
            check("zero BEB cap exhausts exactly four attempts per frame", t["txAttempts"] == 8 and t["collisions"] == 8 and t["dropped"] == 2)
    _, n, _ = run("TestWarmupArrival"); t = totals(n)
    check("arrival exactly at warmup belongs to measurement", t["initialPending"] == 0 and t["generated"] == 1 and t["success"] == 1)
    _, n, _ = run("TestWarmupCompletion"); t = totals(n)
    check("completion at warmup resolves an initial pending attempt", t["initialPending"] == 1 and t["generated"] == 0 and t["success"] == 1 and t["txAttempts"] == 0 and t["resolvedAttempts"] == 1)
    _, n, _ = run("TestBeforeWarmup"); t = totals(n)
    check("termination before warmup records zero measurement interval", all(x["measurementTime"] == 0 for x in n.values()) and t["initialPending"] == 1 and t["finalPending"] == 1 and all(t[key] == 0 for key in TOTAL_KEYS if key not in ("initialPending", "finalPending")))
    _, n, _ = run("CsmaCd", 0, ["--sim-time-limit=0.1s", "--warmup-period=0.01s"], "repro-a")
    _, m, _ = run("CsmaCd", 0, ["--sim-time-limit=0.1s", "--warmup-period=0.01s"], "repro-b")
    check("same seed reproduces all node scalars", n.keys() == m.keys() and all(n[k].keys() == m[k].keys() and all(v == m[k][s] or (math.isnan(v) and math.isnan(m[k][s])) for s, v in n[k].items()) for k in n))
    for protocol in ("aloha", "slotted"):
        _, other, _ = run("CsmaCd", 0, ["--sim-time-limit=0.1s", "--warmup-period=0.01s", f'--**.protocol="{protocol}"'], f"traffic-{protocol}")
        check(f"{protocol} receives the identical offered traffic", n.keys() == other.keys() and all(n[k]["generated"] == other[k]["generated"] for k in n))
    _, n, _ = run("CsmaCd", 0, ["--sim-time-limit=0.1s", "--warmup-period=0.01s", "--**.queueLimit=1", "--**.G=20"], "overflow")
    check("queue overflow is recorded and conserves packets", totals(n)["blocked"] > 0)
    require_unchanged(baseline)
    write_json(result_path, {"passed": checks, **baseline})
    print(f"PASS: {len(checks)} integration checks", flush=True)


def experiments(configs):
    configs = list(dict.fromkeys(configs))
    baseline = provenance()
    plans = {config: query_runs(config) for config in configs}
    dest = ROOT / "results/verified"
    dest.mkdir(parents=True, exist_ok=True)
    version = subprocess.run([str(ROOT / "BTL_MMT.exe"), "-v"], cwd=ROOT, env=environment(),
                             capture_output=True, text=True, check=True).stdout
    manifest = {"schema": 1, "status": "running", "tool_version": version,
                "platform": platform.platform(), "python": sys.version,
                "configs": {c: len(numbers) for c, numbers in plans.items()}, "runs": [], **baseline}
    path = dest / "manifest.json"
    write_json(path, manifest)
    try:
        for config, numbers in plans.items():
            for index in numbers:
                require_unchanged(baseline)
                attrs, nodes, elapsed = run(config, index, folder="verified")
                require_unchanged(baseline)
                scalar = dest / f"{config}-{index}.sca"
                _, _, parameters = read_results(scalar)
                record = {"config": config, "run": index, "seed": attrs["seedset"],
                          "repetition": attrs["repetition"], "seconds": elapsed,
                          "measurementTime": next(iter(nodes.values()))["measurementTime"],
                          "parameters": actual_parameters(parameters, nodes), "files": {}}
                for suffix in ("sca", "vec", "vci", "log"):
                    output = dest / f"{config}-{index}.{suffix}"
                    if output.exists():
                        record["files"][output.relative_to(ROOT).as_posix()] = sha256(output)
                manifest["runs"].append(record)
                write_json(path, manifest)
                if index % 10 == 0:
                    print(f"{config}: {index + 1}/{len(numbers)}", flush=True)
        require_unchanged(baseline)
        manifest["status"] = "complete"
        write_json(path, manifest)
    except BaseException:
        manifest["status"] = "failed"
        write_json(path, manifest)
        raise


def verified_records(root=ROOT):
    """Read only a complete, unchanged batch; never infer provenance from a glob."""
    path = root / "results/verified/manifest.json"
    if not path.exists():
        raise ValueError("Missing manifest; run python scripts/run.py experiments first")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("status") != "complete":
        raise ValueError("Experiment manifest is incomplete or unsupported")
    require_unchanged({k: manifest[k] for k in ("sources", "executable_sha256", "build_info_sha256")}, root)
    configs = manifest.get("configs", {})
    if not configs or any(c not in CONFIGS or count != CONFIGS[c] for c, count in configs.items()):
        raise ValueError("Manifest configuration matrix does not match the experiment plan")
    expected = {(c, i) for c, count in configs.items() for i in range(count)}
    records = manifest.get("runs", [])
    observed = [(r["config"], r["run"]) for r in records]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("Manifest is missing runs or contains duplicate/unexpected runs")
    for record in records:
        scalar_name = f"results/verified/{record['config']}-{record['run']}.sca"
        if scalar_name not in record.get("files", {}):
            raise ValueError(f"Missing scalar hash: {scalar_name}")
        for name, digest in record["files"].items():
            output = (root / name).resolve()
            if output.parent != (root / "results/verified").resolve():
                raise ValueError(f"Output path outside verified folder: {name}")
            if not output.is_file() or sha256(output) != digest:
                raise ValueError(f"Missing or changed result: {name}")
        attrs, nodes, parameters = read_results(root / scalar_name)
        validate_nodes(nodes, scalar_name)
        if (attrs.get("configname") != record["config"] or
                attrs.get("runnumber") != str(record["run"]) or
                attrs.get("seedset") != str(record["seed"]) or
                attrs.get("repetition") != str(record["repetition"]) or
                actual_parameters(parameters, nodes) != record["parameters"] or
                next(iter(nodes.values()))["measurementTime"] != record["measurementTime"]):
            raise ValueError(f"Run metadata does not match manifest: {scalar_name}")
        yield record, attrs, nodes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["test", "experiments", "record-build"])
    parser.add_argument("--configs", nargs="+", choices=list(CONFIGS), default=list(CONFIGS))
    args = parser.parse_args()
    if args.mode == "record-build":
        record_build()
    elif args.mode == "test":
        provenance()
        test()
    else:
        experiments(args.configs)

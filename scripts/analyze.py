"""Validate a complete manifest, aggregate raw scalars, and regenerate figures."""
import csv
from collections import defaultdict
import math
import re
import statistics
from run import ROOT, verified_records, totals

METRICS = ("success", "retransmissions", "S", "throughput_bps", "G_attempt", "G_arrival",
           "collision_ratio", "delay_s", "retry_per_attempt", "loss_ratio")
GROUP_KEYS = ("config", "G", "N", "a", "beb", "measurement_time_s", "frame_bits",
              "bitrate_bps", "queue_limit", "max_attempts", "retx_window", "protocol",
              "settlement_time_s", "slotted_period_s", "phy_model_version")


def numeric_parameter(value, unit=""):
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)" + re.escape(unit), str(value))
    if not match:
        raise ValueError(f"Expected numeric parameter with unit {unit!r}: {value}")
    result = float(match.group(1))
    if not math.isfinite(result):
        raise ValueError(f"Nonfinite parameter: {value}")
    return result


def rows_from_records(records):
    rows = []
    for record, attrs, nodes in records:
        t = totals(nodes)
        sample = next(iter(nodes.values()))
        duration = sample["measurementTime"]
        if duration <= 0:
            raise ValueError("No measurement interval")
        p = record["parameters"]
        ratio = lambda numerator, denominator: numerator / denominator if denominator else float("nan")
        row = {"config": record["config"], "run": record["run"], "seed": int(record["seed"]),
               "G": numeric_parameter(p["G"]), "N": p["numNodes"],
               "a": numeric_parameter(p["maxPropDelay"], "s") / sample["frameTime"],
               "beb": int(p["maxBackoffExp"]), "measurement_time_s": duration,
               "frame_bits": sample["frameBits"], "bitrate_bps": numeric_parameter(p["bitrate"], "bps"),
               "queue_limit": int(p["queueLimit"]), "max_attempts": int(p["maxAttempts"]),
               "retx_window": int(p["retxWindow"]), "protocol": p["protocol"].strip('"'),
               "settlement_time_s": sample["propagationTime"],
               "slotted_period_s": sample["alohaSlotTime"], "phy_model_version": sample["phyModelVersion"]}
        row.update(t)
        row.update(S=t["success"] * sample["frameTime"] / duration,
                   throughput_bps=t["success"] * sample["frameBits"] / duration,
                   G_attempt=t["txAttempts"] * sample["frameTime"] / duration,
                   G_arrival=t["generated"] * sample["frameTime"] / duration,
                   collision_ratio=ratio(t["collisions"], t["resolvedAttempts"]),
                   delay_s=ratio(t["delaySum"], t["success"]),
                   retry_per_attempt=ratio(t["retransmissions"], t["txAttempts"]),
                   loss_ratio=ratio(t["blocked"] + t["dropped"], t["generated"]))
        rows.append(row)
    if not rows:
        raise ValueError("No verified experiment runs")
    return rows


def validate_comparison(rows):
    """Reject comparisons that mix physical conditions or offered traffic."""
    protocols = {"CsmaCd": "csmacd", "Aloha": "aloha", "Slotted": "slotted"}
    controls = tuple(k for k in GROUP_KEYS if k not in ("config", "protocol"))
    groups = defaultdict(list)
    grids = defaultdict(set)
    for row in rows:
        if row["config"] in protocols:
            if row["protocol"] != protocols[row["config"]]:
                raise ValueError("Unexpected MAC in protocol comparison")
            groups[row["G"], row["seed"]].append(row)
            grids[row["config"]].add((row["G"], row["seed"]))
    if len({frozenset(grid) for grid in grids.values()}) > 1:
        raise ValueError("Different load/seed grids in protocol comparison")
    for key, runs in groups.items():
        if len({tuple(r[k] for k in controls) for r in runs}) > 1:
            raise ValueError(f"Different physical/traffic controls in comparison: {key}")
        if len({r["generated"] for r in runs}) > 1:
            raise ValueError(f"Different offered traffic in comparison: {key}")


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in GROUP_KEYS)].append(row)
    summary = []
    for key, runs in sorted(groups.items()):
        row = dict(zip(GROUP_KEYS, key))
        row["runs"] = len(runs)
        if len(runs) != 5 or {r["seed"] for r in runs} != set(range(5)):
            raise ValueError(f"Expected seeds 0–4 exactly once: {key}")
        for metric in METRICS:
            values = [r[metric] for r in runs if math.isfinite(r[metric])]
            row[metric + "_valid_runs"] = len(values)
            row[metric + "_mean"] = statistics.mean(values) if values else float("nan")
            row[metric + "_sd"] = statistics.stdev(values) if len(values) >= 2 else float("nan")
        summary.append(row)
    return summary


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def stability_comparison(summary):
    result = []
    short = {r["G"]: r for r in summary if r["config"] == "CsmaCd"}
    for longer in (r for r in summary if r["config"] == "Stability"):
        if longer["G"] not in short:
            continue
        shorter = short[longer["G"]]
        for metric in ("S", "collision_ratio", "delay_s", "loss_ratio"):
            before, after = shorter[metric + "_mean"], longer[metric + "_mean"]
            result.append({"G": longer["G"], "metric": metric,
                           "short_measurement_s": shorter["measurement_time_s"],
                           "long_measurement_s": longer["measurement_time_s"],
                           "short_mean": before, "short_sd": shorter[metric + "_sd"],
                           "long_mean": after, "long_sd": longer[metric + "_sd"],
                           "relative_change": (after - before) / before if before else float("nan")})
    return result


def plot_results(summary, plots):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 11, "figure.dpi": 150,
                         "axes.spines.top": False, "axes.spines.right": False})
    count = 0

    def series(ax, rows, x, metric, label):
        rows = sorted((r for r in rows if math.isfinite(r[metric + "_mean"])), key=lambda r: r[x])
        if not rows:
            return
        ax.errorbar([r[x] for r in rows], [r[metric + "_mean"] for r in rows],
                    yerr=[r[metric + "_sd"] if math.isfinite(r[metric + "_sd"]) else 0 for r in rows],
                    marker="o", capsize=3, label=label)

    def save(fig, ax, name):
        nonlocal count
        if ax.lines:
            ax.legend()
        ax.grid(alpha=.2)
        fig.tight_layout()
        fig.savefig(plots / f"{name}.png")
        plt.close(fig)
        count += 1

    comparison_metrics = [("S", "Normalized throughput S"), ("collision_ratio", "Collided / resolved attempts"),
                          ("delay_s", "Mean completed-frame delay (s)"),
                          ("loss_ratio", "Blocked + dropped / generated"),
                          ("success", "Successful frames in measurement interval"),
                          ("retransmissions", "Retransmission attempts in measurement interval")]
    available = {r["config"] for r in summary}
    for metric, label in comparison_metrics:
        if not available.intersection({"CsmaCd", "Aloha", "Slotted"}):
            continue
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for config in ("CsmaCd", "Aloha", "Slotted"):
            series(ax, [r for r in summary if r["config"] == config], "G", metric, config)
        ax.set(xlabel="New-frame offered load G", ylabel=label,
               title="Protocol comparison | 10 nodes | mean ± sample SD, 5 seeds")
        save(fig, ax, f"comparison_{metric}")
    for config, x, label in [("StudyN", "N", "Number of nodes"),
                             ("StudyA", "a", "Propagation / frame time"),
                             ("StudyBEB", "beb", "Maximum BEB exponent")]:
        if config not in available:
            continue
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for load in sorted({r["G"] for r in summary if r["config"] == config}):
            series(ax, [r for r in summary if r["config"] == config and r["G"] == load], "G" if x == "G" else x, "S", f"G={load}")
        ax.set(xlabel=label, ylabel="Normalized throughput S", title=f"{config} | mean ± sample SD, 5 seeds")
        save(fig, ax, config)
    if {"Stability", "CsmaCd"}.issubset(available):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        loads = {r["G"] for r in summary if r["config"] == "Stability"}
        for config, label in (("CsmaCd", "20s run / 2s warmup"), ("Stability", "100s run / 10s warmup")):
            series(ax, [r for r in summary if r["config"] == config and r["G"] in loads], "G", "S", label)
        ax.set(xlabel="New-frame offered load G", ylabel="Normalized throughput S",
               title="CSMA/CD duration check | mean ± sample SD, 5 seeds")
        save(fig, ax, "Stability")
    return count


def analyze():
    # Fully validate all records and seeds before writing derived products.
    rows = rows_from_records(list(verified_records()))
    validate_comparison(rows)
    summary = summarize(rows)
    out = ROOT / "results/summary"
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "runs.csv", rows)
    write_csv(out / "summary.csv", summary)
    stability = stability_comparison(summary)
    if stability:
        write_csv(out / "stability.csv", stability)
    else:
        (out / "stability.csv").unlink(missing_ok=True)
    plots = ROOT / "plots"
    plots.mkdir(exist_ok=True)
    owned_plots = [f"comparison_{metric}" for metric in ("S", "collision_ratio", "delay_s", "loss_ratio", "success", "retransmissions")]
    owned_plots += ["StudyN", "StudyA", "StudyBEB", "Stability"]
    for name in owned_plots:
        (plots / f"{name}.png").unlink(missing_ok=True)
    count = plot_results(summary, plots)
    print(f"Aggregated {len(rows)} verified runs into {len(summary)} parameter groups; {count} plots")
    print("Undefined ratios/delays remain NaN; *_valid_runs reports the seeds contributing to each metric.")
    return summary


if __name__ == "__main__":
    analyze()

"""Run in a small Linux container to sample total Docker VM memory, not RSS sums.

/proc/meminfo reports the VM's guest memory on Docker Desktop. This is sampled
used memory (MemTotal - MemAvailable), not a guarantee about peaks between samples.
"""
import argparse
import json
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--seconds", type=int, default=60)
args = parser.parse_args()
if not 1 <= args.seconds <= 86400:
    parser.error("--seconds must be between 1 and 86400")
peak = 0
samples = 0
for second in range(args.seconds):
    fields = {line.split(":")[0]: int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line and line.split()[1].isdigit()}
    used = fields["MemTotal"] - fields["MemAvailable"]
    peak = max(peak, used)
    samples += 1
    time.sleep(1)
print(json.dumps({"sample_count": samples, "interval_seconds": 1, "total_bytes": fields["MemTotal"],
                  "peak_used_bytes": peak, "peak_used_gib": round(peak / 1024 ** 3, 3),
                  "recommend_reducing_demo_workload": peak > 6.5 * 1024 ** 3}))

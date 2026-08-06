#!/bin/bash
# Regenerates data/rollout_report.html every 10 minutes while the full run proceeds.
cd /workspace/SLAVA_dev
while true; do
  /opt/miniforge3/bin/conda run -n slava-notebook python scripts/generate_rollout_report.py >> rollouts/final/pilot_v0/logs/report_loop.log 2>&1
  sleep 600
done

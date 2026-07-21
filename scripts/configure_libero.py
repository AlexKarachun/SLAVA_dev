#!/usr/bin/env python3
"""Create LIBERO's path config without triggering its interactive first import."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    benchmark_root = repo / "libero" / "libero"
    required = [
        benchmark_root / "bddl_files",
        benchmark_root / "init_files",
        benchmark_root / "assets",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"LIBERO repository is incomplete; missing: {missing}")

    config = {
        "benchmark_root": str(benchmark_root),
        "bddl_files": str(benchmark_root / "bddl_files"),
        "init_states": str(benchmark_root / "init_files"),
        "datasets": str(repo / "libero" / "datasets"),
        "assets": str(benchmark_root / "assets"),
    }
    args.config_dir.mkdir(parents=True, exist_ok=True)
    config_path = args.config_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(f"Wrote {config_path}")


if __name__ == "__main__":
    main()

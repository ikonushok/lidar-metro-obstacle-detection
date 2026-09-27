"""Check that the submission repository does not track local data or secrets.

The script is intentionally read-only. It verifies a small set of release
invariants before pushing the hackathon repository.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


FORBIDDEN_TRACKED_RE = re.compile(
    r"(^|/)dataset(/|$)"
    r"|(^|/)artefacts(/|$)"
    r"|(^|/)log(/|$)"
    r"|(^|/)tmp(/|$)"
    r"|\.(db3|bag|mcap|pcd|las|laz|tar|zst|mp4|mov|avi|mkv|pptx|pem|key)$"
    r"|(^|/)\.env(\.|$)"
)

REQUIRED_PATHS = (
    "README.md",
    "SOLUTION.md",
    "Dockerfile",
    "models/noise_classifier_candidate_baseline_v2.json",
    "scripts/build_current_model_validation_dataset.py",
    "scripts/evaluate_current_model_real_synthetic.py",
    "scripts/prepare_hackathon_datasets.py",
    "scripts/run_stage_2_cpu_player.ps1",
    "scripts/check_submission_package.py",
    "docs/README_REVIEWER_PLAYER_QUICKSTART.md",
    "docs/README_SUBMISSION_CHECKLIST.md",
    "src/lidar_mosmetro3d_cpp/package.xml",
    "src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp",
)

REQUIRED_GITIGNORE_TOKENS = (
    "/dataset/",
    "/artefacts/",
    "*.db3",
    "*.tar",
    "*.zst",
    "*.mp4",
    "*.pptx",
    ".env",
)


def run_git(repo: Path, args: list[str]) -> list[str]:
    command = ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args]
    result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [line for line in result.stdout.splitlines() if line.strip()]


def tracked_files(repo: Path) -> list[str]:
    return run_git(repo, ["ls-files"])


def changed_files(repo: Path) -> list[str]:
    return run_git(repo, ["status", "--short"])


def check_required_paths(repo: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_PATHS:
        if not (repo / relative).exists():
            errors.append(f"missing required path: {relative}")
    return errors


def check_forbidden_tracked(paths: list[str]) -> list[str]:
    return [f"forbidden tracked file: {path}" for path in paths if FORBIDDEN_TRACKED_RE.search(path.replace("\\", "/"))]


def check_large_tracked(repo: Path, paths: list[str], max_bytes: int) -> list[str]:
    errors: list[str] = []
    for relative in paths:
        path = repo / relative
        if path.is_file() and path.stat().st_size > max_bytes:
            errors.append(f"tracked file is larger than {max_bytes} bytes: {relative} ({path.stat().st_size} bytes)")
    return errors


def check_gitignore(repo: Path) -> list[str]:
    gitignore = repo / ".gitignore"
    if not gitignore.exists():
        return ["missing required path: .gitignore"]
    text = gitignore.read_text(encoding="utf-8", errors="replace")
    return [f".gitignore misses token: {token}" for token in REQUIRED_GITIGNORE_TOKENS if token not in text]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--max-bytes", type=int, default=10 * 1024 * 1024, help="maximum tracked file size")
    parser.add_argument("--require-clean", action="store_true", help="fail if the worktree has uncommitted changes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()

    errors: list[str] = []
    try:
        paths = tracked_files(repo)
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stderr)
        return 2

    errors.extend(check_required_paths(repo))
    errors.extend(check_forbidden_tracked(paths))
    errors.extend(check_large_tracked(repo, paths, args.max_bytes))
    errors.extend(check_gitignore(repo))

    if args.require_clean:
        dirty = changed_files(repo)
        errors.extend(f"worktree is not clean: {line}" for line in dirty)

    if errors:
        print("SUBMISSION CHECK FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: submission package checks passed for {repo}")
    print(f"tracked files: {len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Prepare local hackathon datasets for the direct player and optional ROS2 runs.

The direct CPU player reads uncompressed TAR archives lazily from
dataset/for_hackathon. Full extraction is optional and should be used only for
selected bags that must be replayed with ros2 bag play.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


ARCHIVES = {
    "for_hackathon": {
        "candidates": ("for_hackathon", "for_hackathon.tar", "for_hackathon.zst", "for_hackathon.tar.zst"),
        "required": ("for_hackathon/doubleT_obstacle/metadata.yaml",),
    },
    "new_data": {
        "candidates": ("new_data", "new_data.tar", "new_data.zst", "new_data.tar.zst"),
        "required": ("new_data/metadata.yaml",),
    },
    "cloud_with_fake_obj": {
        "candidates": (
            "cloud_with_fake_obj",
            "cloud_with_fake_obj.tar",
            "cloud_with_fake_obj.zst",
            "cloud_with_fake_obj.tar.zst",
        ),
        "required": ("cloud_with_fake_obj/metadata.yaml",),
    },
}

BAGS = {
    "roundT_doubleT": ("for_hackathon", "for_hackathon/roundT_doubleT"),
    "squareT_platform_squareT_switch": ("for_hackathon", "for_hackathon/squareT_platform_squareT_switch"),
    "doubleT_platform": ("for_hackathon", "for_hackathon/doubleT_platform"),
    "roundT_squareT_pressureGate_squareT": ("for_hackathon", "for_hackathon/roundT_squareT_pressureGate_squareT"),
    "doubleT_obstacle": ("for_hackathon", "for_hackathon/doubleT_obstacle"),
    "roundT_pressureGate_roundT": ("for_hackathon", "for_hackathon/roundT_pressureGate_roundT"),
    "cloud_with_fake_obj": ("cloud_with_fake_obj", "cloud_with_fake_obj"),
}


def is_zstd(path: Path) -> bool:
    with path.open("rb") as source:
        return source.read(4) == b"\x28\xb5\x2f\xfd"


def validate_tar(path: Path, required_members: tuple[str, ...]) -> None:
    try:
        with tarfile.open(path, "r:") as archive:
            names = {member.name.lstrip("./") for member in archive.getmembers()}
    except tarfile.TarError as error:
        raise ValueError(f"{path} is not an uncompressed TAR archive") from error
    missing = [name for name in required_members if name not in names]
    if missing:
        raise ValueError(f"{path} misses expected member(s): {', '.join(missing)}")


def find_raw(raw_dir: Path, archive_id: str) -> Path:
    for name in ARCHIVES[archive_id]["candidates"]:
        candidate = raw_dir / name
        if candidate.is_file():
            return candidate
    expected = ", ".join(ARCHIVES[archive_id]["candidates"])
    raise FileNotFoundError(f"put one of [{expected}] into {raw_dir}")


def materialize_archive(raw_dir: Path, catalog_dir: Path, archive_id: str, copy: bool) -> Path:
    catalog_dir.mkdir(parents=True, exist_ok=True)
    target = catalog_dir / archive_id
    if target.exists():
        validate_tar(target, ARCHIVES[archive_id]["required"])
        print(f"OK existing {target}")
        return target

    source = find_raw(raw_dir, archive_id)
    if source.resolve() == target.resolve():
        validate_tar(target, ARCHIVES[archive_id]["required"])
        print(f"OK source already in place {target}")
        return target

    if source.suffix == ".zst" or is_zstd(source):
        zstd = shutil.which("zstd")
        if zstd is None:
            raise RuntimeError(f"{source} is zstd-compressed; install zstd or unpack it to {target}")
        temp_target = target.with_name(target.name + ".tmp")
        temp_target.unlink(missing_ok=True)
        with temp_target.open("wb") as output:
            subprocess.run([zstd, "-d", "-c", str(source)], stdout=output, check=True)
        validate_tar(temp_target, ARCHIVES[archive_id]["required"])
        temp_target.replace(target)
        print(f"decompressed {source} -> {target}")
        return target

    if copy:
        temp_target = target.with_name(target.name + ".tmp")
        temp_target.unlink(missing_ok=True)
        shutil.copyfile(source, temp_target)
        validate_tar(temp_target, ARCHIVES[archive_id]["required"])
        temp_target.replace(target)
        action = "copied"
    else:
        try:
            os.link(source, target)
            action = "hardlinked"
        except OSError:
            temp_target = target.with_name(target.name + ".tmp")
            temp_target.unlink(missing_ok=True)
            shutil.copyfile(source, temp_target)
            validate_tar(temp_target, ARCHIVES[archive_id]["required"])
            temp_target.replace(target)
            action = "copied"
    validate_tar(target, ARCHIVES[archive_id]["required"])
    print(f"{action} {source} -> {target}")
    return target


def safe_target(root: Path, relative_name: str) -> Path:
    target = (root / relative_name).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"unsafe archive path: {relative_name}")
    return target


def extract_bag(catalog_dir: Path, extracted_dir: Path, bag_id: str) -> None:
    archive_id, prefix = BAGS[bag_id]
    archive_path = catalog_dir / archive_id
    target_root = extracted_dir / bag_id
    target_root.mkdir(parents=True, exist_ok=True)
    selected = 0
    with tarfile.open(archive_path, "r:") as archive:
        for member in archive.getmembers():
            name = member.name.lstrip("./")
            if not name.startswith(prefix.rstrip("/") + "/") or not member.isfile():
                continue
            relative = name[len(prefix.rstrip("/")) + 1 :]
            target = safe_target(target_root, relative)
            if target.exists():
                print(f"skip existing {target}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as output:
                if source is None:
                    raise ValueError(f"cannot read archive member: {name}")
                shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
            selected += 1
            print(f"extracted {name} -> {target}")
    if selected == 0 and not any(target_root.iterdir()):
        raise ValueError(f"no files extracted for {bag_id} from {archive_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("dataset/raw"))
    parser.add_argument("--catalog-dir", type=Path, default=Path("dataset/for_hackathon"))
    parser.add_argument("--extracted-dir", type=Path, default=Path("dataset/extracted"))
    parser.add_argument("--copy", action="store_true", help="copy archives instead of trying hardlinks first")
    parser.add_argument(
        "--extract",
        action="append",
        choices=sorted(BAGS),
        default=[],
        help="also extract this selected ROS2 bag into dataset/extracted",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for archive_id in ARCHIVES:
        materialize_archive(args.raw_dir, args.catalog_dir, archive_id, args.copy)
    for bag_id in args.extract:
        extract_bag(args.catalog_dir, args.extracted_dir, bag_id)
    print("OK: datasets are ready for the direct CPU player")


if __name__ == "__main__":
    main()

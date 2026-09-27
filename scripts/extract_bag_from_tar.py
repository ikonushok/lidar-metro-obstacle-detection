"""Extract one named ROS2 bag from a local uncompressed TAR without overwrite."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tarfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("dataset/for_hackathon/for_hackathon"))
    parser.add_argument("--bag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    names = ("metadata.yaml", f"{args.bag}_0.db3")
    with tarfile.open(args.archive, "r:") as archive:
        for name in names:
            member = archive.getmember(f"for_hackathon/{args.bag}/{name}")
            if not member.isfile():
                raise ValueError(f"not a regular file: {member.name}")
            target = args.output / args.bag / name
            if target.exists():
                raise FileExistsError(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination, length=8 * 1024 * 1024)
            print(f"{target} {member.size}", flush=True)


if __name__ == "__main__":
    main()

"""Concatenate source-part previews while retaining explicit chapter boundaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def ffconcat_path(path: Path) -> str:
    return "file '" + str(path.resolve()).replace("'", r"'\\''") + "'\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = json.loads(args.preview_manifest.read_text(encoding="utf-8"))
    chapters = manifest.get("source_part_chapters", [])
    if len(chapters) != 221:
        raise ValueError("expected one preview chapter for each of 221 source parts")
    root = args.preview_manifest.parent.parent
    sources = [root / chapter["video"] for chapter in chapters]
    if any(not source.is_file() for source in sources):
        raise FileNotFoundError("preview video listed by manifest is missing")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    duration_ms = 4000  # 12 frames / 3 fps, verified by preview manifest below.
    if any(chapter.get("fps") != 3.0 or len(chapter.get("sampled_catalog_indices", [])) != 12 for chapter in chapters):
        raise ValueError("preview duration is not the expected fixed 4 seconds")
    with tempfile.TemporaryDirectory(prefix="cpp-preview-concat-") as temporary:
        temporary = Path(temporary)
        concat = temporary / "inputs.ffconcat"
        metadata = temporary / "chapters.ffmeta"
        concat.write_text("ffconcat version 1.0\n" + "".join(ffconcat_path(source) for source in sources), encoding="utf-8")
        lines = [";FFMETADATA1", "title=new_data C++ development_candidate source-part previews",
                 "comment=Diagnostic only; CORE is a C++ candidate; UNKNOWN is not CLEAR."]
        chapter_index = []
        for position, chapter in enumerate(chapters):
            start = position * duration_ms
            end = start + duration_ms
            title = f"source-part {chapter['part_index']:03d}; frames {chapter['frame_interval_inclusive'][0]}-{chapter['frame_interval_inclusive'][1]}"
            lines.extend(["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}", f"title={title}"])
            chapter_index.append({"chapter": position, "start_ms": start, "end_ms": end, "title": title,
                                  "video": chapter["video"], "source_part": chapter["source_part"],
                                  "frame_interval_inclusive": chapter["frame_interval_inclusive"]})
        metadata.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(metadata),
                        "-map_metadata", "1", "-c", "copy", "-movflags", "+faststart", str(args.output)], check=True)
    sidecar = args.output.with_suffix(".chapters.json")
    sidecar.write_text(json.dumps({"video": args.output.name, "chapters": chapter_index,
                                   "scope": "DIAGNOSTIC_PREVIEW_ONLY; source-part boundaries retained"},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "chapters": len(chapter_index), "sidecar": str(sidecar)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

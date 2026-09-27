"""Generate the C++ candidate_baseline_v2 forest-lite include from JSON."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models/noise_classifier_candidate_baseline_v2.json"
OUTPUT = ROOT / "src/cpp/candidate_baseline_v2_model.inc"


def emit_tree(node: dict, indent: int) -> str:
    space = "  " * indent
    if "feature_index" not in node:
        positive = node["positive_weight"]
        negative = node["negative_weight"]
        total = positive + negative
        probability = 0.0 if not total else positive / total
        return f"{space}return {probability:.17g};\n"
    text = f"{space}if (features[{node['feature_index']}] <= {node['threshold']:.17g}) {{\n"
    text += emit_tree(node["left"], indent + 1)
    text += f"{space}}} else {{\n"
    text += emit_tree(node["right"], indent + 1)
    text += f"{space}}}\n"
    return text


def main() -> None:
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    lines = [
        "// Generated from models/noise_classifier_candidate_baseline_v2.json. Do not edit by hand.\n",
        f"constexpr double kCandidateBaselineV2Threshold = {model['threshold']:.17g};\n",
        'constexpr const char* kCandidateBaselineV2Name = "candidate_baseline_v2";\n\n',
    ]
    for index, tree in enumerate(model["trees"]):
        lines.append(f"double CandidateBaselineV2Tree{index}(const std::array<double, 8>& features) {{\n")
        lines.append(emit_tree(tree, 1))
        lines.append("}\n\n")
    lines.append("double CandidateBaselineV2Score(const std::array<double, 8>& features) {\n")
    lines.append("  double score = 0.0;\n")
    for index in range(len(model["trees"])):
        lines.append(f"  score += CandidateBaselineV2Tree{index}(features);\n")
    lines.append(f"  return score / {float(len(model['trees'])):.1f};\n")
    lines.append("}\n")
    OUTPUT.write_text("".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "trees": len(model["trees"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()

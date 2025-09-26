"""
DinoScan Import Time Budget Estimator

This script analyzes all Python modules in the workspace and estimates their import time budget.
It uses AST parsing to identify top-level imports and static complexity, then produces a report
listing estimated import costs for each module.

- For each .py file:
    - Parse AST, find all top-level imports
    - Estimate cost: number of imports, presence of known heavy modules (e.g., numpy, pandas, requests)
    - Optionally, count top-level statements (functions/classes/assignments)
    - Output: module path, import count, heavy import flag, complexity score

Output: import_time_budget_report.json
"""

import ast
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

# Known heavy modules (can be expanded)
HEAVY_MODULES = {"numpy", "pandas", "requests", "torch", "tensorflow", "scipy", "sklearn"}


REPORT_PATH = "import_time_budget_report.json"
COLD_START_REPORT_PATH = "cold_start_hotspots_report.json"
DINOQA_SCORE_PATH = "dinoqa_score.json"


def _collect_imports(tree: ast.AST) -> tuple[set, set]:
    imports = set()
    heavy_imports = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                imports.add(mod)
                if mod in HEAVY_MODULES:
                    heavy_imports.add(mod)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module.split(".")[0]
            imports.add(mod)
            if mod in HEAVY_MODULES:
                heavy_imports.add(mod)
    return imports, heavy_imports


def _count_top_level(tree: ast.AST) -> int:
    count = 0
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign)):
            count += 1
    return count


def analyze_imports_in_file(filepath: Path) -> dict | None:
    try:
        with filepath.open(encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except Exception:
        return None  # Skip files with parse errors
    imports, heavy_imports = _collect_imports(tree)
    top_level_count = _count_top_level(tree)
    return {
        "imports": list(imports),
        "heavy_imports": list(heavy_imports),
        "top_level_count": top_level_count,
    }


def build_reverse_import_graph(results: dict) -> dict[str, set]:
    reverse_graph: dict[str, set] = {}
    for importer, data in results.items():
        for imported in data["imports"]:
            if imported not in reverse_graph:
                reverse_graph[imported] = set()
            reverse_graph[imported].add(importer)

    return reverse_graph


def cold_start_hotspot_analysis(results: dict) -> dict:
    reverse_graph = build_reverse_import_graph(results)
    hotspots = {
        mod: list(importers) for mod, importers in reverse_graph.items() if len(importers) > 1
    }
    sorted_hotspots = sorted(hotspots.items(), key=lambda x: len(x[1]), reverse=True)
    return dict(sorted_hotspots)


def walk_python_files(root_dir: Path) -> "Generator[Path, None, None]":
    yield from root_dir.rglob("*.py")


def compute_dinoqa_score(results: dict, hotspots: dict) -> dict:
    # Example scoring logic:
    # - Penalize high complexity scores (import cost)
    # - Penalize many cold-start hotspots
    # - Reward low heavy import usage
    total_files = len(results)
    total_complexity = sum(mod["complexity_score"] for mod in results.values())
    avg_complexity = total_complexity / max(total_files, 1)
    heavy_imports_count = sum(len(mod["heavy_imports"]) for mod in results.values())
    hotspot_count = len(hotspots)
    # Scoring: lower is better for complexity, heavy imports, hotspots
    score = 100
    score -= int(avg_complexity * 1.5)  # penalize high complexity
    score -= int(heavy_imports_count * 1.2)  # penalize heavy imports
    score -= int(hotspot_count * 0.8)  # penalize hotspots
    score = max(0, min(100, score))
    return {
        "dinoqa_score": score,
        "avg_complexity": avg_complexity,
        "heavy_imports_count": heavy_imports_count,
        "hotspot_count": hotspot_count,
        "total_files": total_files,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    workspace = Path(__file__).parent.resolve()
    results = {}
    for pyfile in walk_python_files(workspace):
        relpath = str(pyfile.relative_to(workspace))
        analysis = analyze_imports_in_file(pyfile)
        if analysis is None:
            continue
        # Simple complexity score: import count + 2*heavy_imports + top_level_count
        score = (
            len(analysis["imports"])
            + 2 * len(analysis["heavy_imports"])
            + analysis["top_level_count"]
        )
        results[relpath] = {
            "import_count": len(analysis["imports"]),
            "heavy_imports": analysis["heavy_imports"],
            "top_level_count": analysis["top_level_count"],
            "complexity_score": score,
            "imports": analysis["imports"],
        }
    report_path = Path(REPORT_PATH)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logging.info("Import time budget report written to %s", REPORT_PATH)

    # Cold-start hotspot analysis
    hotspots = cold_start_hotspot_analysis(results)
    cold_report_path = Path(COLD_START_REPORT_PATH)
    with cold_report_path.open("w", encoding="utf-8") as f:
        json.dump(hotspots, f, indent=2)
    logging.info("Cold-start hotspot report written to %s", COLD_START_REPORT_PATH)

    # Repository health scoring
    dinoqa = compute_dinoqa_score(results, hotspots)
    dinoqa_path = Path(DINOQA_SCORE_PATH)
    with dinoqa_path.open("w", encoding="utf-8") as f:
        json.dump(dinoqa, f, indent=2)
    logging.info("DinoQA score written to %s", DINOQA_SCORE_PATH)


if __name__ == "__main__":
    main()

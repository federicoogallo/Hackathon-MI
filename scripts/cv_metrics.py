#!/usr/bin/env python3
"""Extract resume evidence without importing the app, loading .env, or calling APIs."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import platform
import xml.etree.ElementTree as ET


def source_metrics(root):
    tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
    registry = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_collectors")
    returned = next(n for n in registry.body if isinstance(n, ast.Return))
    if not isinstance(returned.value, ast.List):
        raise ValueError("Collector registry is no longer a literal list; update extraction.")
    collectors = [n.func.id for n in returned.value.elts if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    if len(collectors) != len(returned.value.elts) or len(set(collectors)) != len(collectors):
        raise ValueError("Unsupported or duplicate collector registration.")
    paths = [root / n for n in ("main.py", "config.py", "models.py")]
    for directory in ("collectors", "filters", "storage", "utils", "notifiers", "tests"):
        paths.extend((root / directory).rglob("*.py"))
    paths.extend((root / ".github/workflows").glob("*.yml"))
    # The parametrized admin regression suite also depends on this versioned corpus.
    paths.append(root / "data/admin_actions.json")
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    return {"registered_collectors": len(collectors), "collector_classes": collectors, "source_sha256": hashes}


def test_metrics(path):
    document = ET.parse(path).getroot()
    cases = list(document.iter("testcase"))
    failed = sum(c.find("failure") is not None for c in cases)
    errors = sum(c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    modules = {}
    for c in cases:
        name = c.attrib.get("classname", "unknown").split(".")
        module = ".".join(name[:2])
        modules[module] = modules.get(module, 0) + 1
    return {
        "collected": len(cases), "passed": len(cases) - failed - errors - skipped,
        "failed": failed, "errors": errors, "skipped": skipped,
        "cases_per_module": dict(sorted(modules.items())),
        "skip_reasons": sorted({c.find("skipped").attrib.get("message", "") for c in cases if c.find("skipped") is not None}),
        "junit_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, help="JUnit XML from the same checkout's pytest run")
    parser.add_argument("--revision", help="Revision tested; use a clean checkout for attributable evidence")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = {"schema_version": 1, "source_revision": args.revision, "python": platform.python_version(), **source_metrics(root)}
    if args.junit:
        report["tests"] = test_metrics(args.junit)
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if args.junit and (report["tests"]["failed"] or report["tests"]["errors"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

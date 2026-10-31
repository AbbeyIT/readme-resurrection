from __future__ import annotations

import json
import ast
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "build",
    "dist", ".idea", ".vscode", ".tox", ".mypy_cache", ".pytest_cache",
    "target", ".resurrect-cache", ".gradle", "vendor", "resurrected",
}

LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".cs": "C#",
    ".kt": "Kotlin", ".swift": "Swift", ".sh": "Shell", ".groovy": "Groovy",
    ".html": "HTML", ".css": "CSS", ".lua": "Lua", ".pl": "Perl",
}

DEPENDENCY_FILES = {
    "package.json", "requirements.txt", "pyproject.toml", "setup.py",
    "Pipfile", "pom.xml", "build.gradle", "go.mod", "Cargo.toml",
    "Gemfile", "composer.json",
}

ENTRY_POINT_NAMES = {
    "main.py", "app.py", "cli.py", "__main__.py", "manage.py", "server.py",
    "index.js", "main.js", "server.js", "app.js", "index.ts", "main.ts",
    "main.go", "main.rs", "Main.java", "Program.cs",
}

LICENSE_MARKERS = [
    ("gnu affero general public license", "AGPL"),
    ("gnu lesser general public license", "LGPL"),
    ("gnu general public license", "GPL"),
    ("mozilla public license", "MPL"),
    ("apache license", "Apache"),
    ("permission is hereby granted, free of charge", "MIT"),
    ("redistribution and use in source and binary forms", "BSD"),
    ("this is free and unencumbered software", "Unlicense"),
    ("isc license", "ISC"),
]


def _detect_license(path: Path) -> str | None:
    text = " ".join(_read(path)[:4000].lower().split())
    for marker, name in LICENSE_MARKERS:
        if marker in text:
            return name
    return None

TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}
MAX_TREE = 2000


@dataclass
class RepoFacts:
    root: str
    name: str
    file_count: int = 0
    total_bytes: int = 0
    tree: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    dependency_files: list[str] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)
    cli_commands: dict[str, str] = field(default_factory=dict)
    make_targets: list[str] = field(default_factory=list)
    test_locations: list[str] = field(default_factory=list)
    license_file: str | None = None
    license_type: str | None = None
    python_requires: str | None = None
    optional_dependencies: dict[str, list[str]] = field(default_factory=dict)
    imports: dict[str, list[str]] = field(default_factory=dict)
    readme_file: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _parse_package_json(path: Path, facts: RepoFacts) -> list[str]:
    try:
        data = json.loads(_read(path))
    except json.JSONDecodeError:
        return []
    names = list(data.get("dependencies", {})) + list(data.get("devDependencies", {}))
    for name, cmd in (data.get("scripts") or {}).items():
        facts.scripts[name] = str(cmd)
    main = data.get("main")
    if isinstance(main, str):
        rel = (path.parent / main).relative_to(Path(facts.root)).as_posix()
        if rel not in facts.entry_points:
            facts.entry_points.append(rel)
    return names


def _parse_requirements(path: Path) -> list[str]:
    names = []
    for line in _read(path).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"[A-Za-z0-9_.\-]+", line)
        if match:
            names.append(match.group(0))
    return names


def _parse_pyproject(path: Path) -> list[str]:
    if tomllib is None:
        return []
    try:
        data = tomllib.loads(_read(path))
    except Exception:
        return []
    deps = list(data.get("project", {}).get("dependencies", []))
    return [m.group(0) for d in deps if (m := re.match(r"[A-Za-z0-9_.\-]+", d))]


def _parse_pyproject_meta(path: Path) -> tuple[str | None, dict[str, list[str]]]:
    """Return (requires-python, {extra name: dependency names})."""
    if tomllib is None:
        return None, {}
    try:
        data = tomllib.loads(_read(path))
    except Exception:
        return None, {}
    project = data.get("project", {})
    extras = {}
    for group, deps in project.get("optional-dependencies", {}).items():
        extras[group] = [m.group(0) for d in deps if (m := re.match(r"[A-Za-z0-9_.\-]+", d))]
    requires = project.get("requires-python")
    return (str(requires) if requires else None), extras


def _is_test_path(rel: str) -> bool:
    parts = rel.lower().split("/")
    return any(p in TEST_DIRS for p in parts[:-1]) or parts[-1].startswith("test_")


def _is_main_guard(node: ast.AST) -> bool:
    """True for `if __name__ == "__main__":` blocks, which hold demo code, not structure."""
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )


def _python_module_names(tree: list[str]) -> dict[str, str]:
    mods = {}
    for rel in sorted(tree):
        if not rel.endswith(".py"):
            continue
        dotted = rel[:-3].replace("/", ".")
        if dotted.endswith(".__init__"):
            dotted = dotted[: -len(".__init__")]
        elif dotted == "__init__":
            continue
        mods[dotted] = rel
    return mods


def _resolve_module(name: str, mods: dict[str, str]) -> str | None:
    if not name:
        return None
    if name in mods:
        return mods[name]
    for dotted, rel in mods.items():  # handles src/ layouts: pkg.mod vs src.pkg.mod
        if dotted.endswith("." + name):
            return rel
    return None


def _python_imports(root: Path, tree: list[str]) -> dict[str, list[str]]:
    """Which repo files import which other repo files, read from the code itself."""
    mods = _python_module_names(tree)
    graph: dict[str, list[str]] = {}
    for rel in tree:
        if not rel.endswith(".py") or _is_test_path(rel):
            continue
        try:
            module = ast.parse(_read(root / rel))
        except (SyntaxError, ValueError):
            continue
        package = rel[:-3].split("/")[:-1]
        found: set[str] = set()
        for top in module.body:
            if _is_main_guard(top):
                continue
            for node in ast.walk(top):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target = _resolve_module(alias.name, mods)
                        if target:
                            found.add(target)
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        base = package[: max(len(package) - (node.level - 1), 0)]
                        prefix = ".".join(base + ([node.module] if node.module else []))
                    else:
                        prefix = node.module or ""
                    for alias in node.names:
                        target = _resolve_module(f"{prefix}.{alias.name}", mods) or _resolve_module(prefix, mods)
                        if target:
                            found.add(target)
        found.discard(rel)
        if found:
            graph[rel] = sorted(found)
    return graph


def _parse_go_mod(path: Path) -> list[str]:
    return re.findall(r"^\s*([\w.\-/]+\.[\w.\-/]+)\s+v[\w.\-+]+", _read(path), re.M)


def _parse_cargo(path: Path) -> list[str]:
    if tomllib is None:
        return []
    try:
        data = tomllib.loads(_read(path))
    except Exception:
        return []
    return list(data.get("dependencies", {}))


def _parse_pom(path: Path) -> list[str]:
    return re.findall(r"<artifactId>([^<]+)</artifactId>", _read(path))


def _parse_makefile(path: Path) -> list[str]:
    targets = re.findall(r"^([A-Za-z0-9_][A-Za-z0-9_.\-]*):(?!=)", _read(path), re.M)
    return sorted(set(targets))

def _parse_pyproject_scripts(path: Path) -> dict[str, str]:
    if tomllib is None:
        return {}
    try:
        data = tomllib.loads(_read(path))
    except Exception:
        return {}
    scripts = data.get("project", {}).get("scripts", {})
    return {str(name): str(target) for name, target in scripts.items()}


def scan(path: str | Path) -> RepoFacts:
    root = Path(path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")

    facts = RepoFacts(root=str(root), name=root.name)
    langs: Counter[str] = Counter()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")
        )
        current = Path(dirpath)
        rel_dir = current.relative_to(root)

        if current != root and current.name.lower() in TEST_DIRS:
            facts.test_locations.append(rel_dir.as_posix())

        for filename in sorted(filenames):
            file_path = current / filename
            rel = (rel_dir / filename).as_posix() if current != root else filename
            facts.file_count += 1
            try:
                facts.total_bytes += file_path.stat().st_size
            except OSError:
                pass
            if len(facts.tree) < MAX_TREE:
                facts.tree.append(rel)

            ext = file_path.suffix.lower()
            if ext in LANGUAGES:
                langs[LANGUAGES[ext]] += 1

            if filename in ENTRY_POINT_NAMES:
                facts.entry_points.append(rel)

            if filename in DEPENDENCY_FILES:
                facts.dependency_files.append(rel)
                if filename == "package.json":
                    names = _parse_package_json(file_path, facts)
                elif filename == "requirements.txt":
                    names = _parse_requirements(file_path)
                elif filename == "pyproject.toml":
                    names = _parse_pyproject(file_path)
                    facts.cli_commands.update(_parse_pyproject_scripts(file_path))
                    requires, extras = _parse_pyproject_meta(file_path)
                    facts.python_requires = facts.python_requires or requires
                    facts.optional_dependencies.update(extras)
                elif filename == "go.mod":
                    names = _parse_go_mod(file_path)
                elif filename == "Cargo.toml":
                    names = _parse_cargo(file_path)
                elif filename == "pom.xml":
                    names = _parse_pom(file_path)
                else:
                    names = []
                if names:
                    facts.dependencies[rel] = names

            lower = filename.lower()
            if current == root:
                if lower.startswith(("license", "copying")) and not facts.license_file:
                    facts.license_file = rel
                    facts.license_type = _detect_license(file_path)
                if lower.startswith("readme") and not facts.readme_file:
                    facts.readme_file = rel
                if filename in ("Makefile", "makefile"):
                    facts.make_targets = _parse_makefile(file_path)

            is_test_file = lower.startswith("test_") or ".test." in lower or ".spec." in lower
            if is_test_file and rel_dir.as_posix() not in facts.test_locations:
                facts.test_locations.append(rel_dir.as_posix() if current != root else ".")

    facts.languages = dict(langs.most_common())
    facts.entry_points = sorted(set(facts.entry_points))
    facts.test_locations = sorted(set(facts.test_locations))
    facts.imports = _python_imports(root, facts.tree)
    return facts


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(scan(target).to_dict(), indent=2))
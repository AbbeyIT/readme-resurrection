import json

from resurrect.scanner import scan


def make_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x")
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n# comment\nflask==3.0\n")
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"express": "^4"}, "scripts": {"start": "node index.js"}})
    )
    (tmp_path / "LICENSE").write_text("MIT")
    (tmp_path / "Makefile").write_text("build:\n\techo hi\ntest:\n\techo t\n")
    return tmp_path


def test_scan_basic(tmp_path):
    facts = scan(make_repo(tmp_path))
    assert facts.languages["Python"] == 2
    assert "src/main.py" in facts.entry_points
    assert "tests" in facts.test_locations
    assert facts.license_file == "LICENSE"
    assert facts.readme_file is None
    assert facts.scripts == {"start": "node index.js"}
    assert facts.make_targets == ["build", "test"]


def test_scan_skips_junk_and_parses_deps(tmp_path):
    facts = scan(make_repo(tmp_path))
    assert not any("node_modules" in f for f in facts.tree)
    assert facts.dependencies["requirements.txt"] == ["requests", "flask"]
    assert facts.dependencies["package.json"] == ["express"]

def test_scan_skips_egg_info_and_reads_cli_commands(tmp_path):
    (tmp_path / "pkg.egg-info").mkdir()
    (tmp_path / "pkg.egg-info" / "PKG-INFO").write_text("x")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[project.scripts]\ndemo = "demo.cli:app"\n'
    )
    facts = scan(tmp_path)
    assert not any("egg-info" in f for f in facts.tree)
    assert facts.cli_commands == {"demo": "demo.cli:app"}

MIT_TEXT = (
    "MIT License\n\nCopyright (c) 2026 Someone\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    "of this software and associated documentation files (the Software), to deal\n"
)


def test_license_type_and_output_folder(tmp_path):
    (tmp_path / "LICENSE").write_text(MIT_TEXT)
    (tmp_path / "resurrected").mkdir()
    (tmp_path / "resurrected" / "README.md").write_text("old output")
    (tmp_path / "main.py").write_text("print('hi')")
    facts = scan(tmp_path)
    assert facts.license_type == "MIT"
    assert not any(f.startswith("resurrected") for f in facts.tree)


def test_unknown_license_type(tmp_path):
    (tmp_path / "LICENSE").write_text("Some custom terms nobody recognizes.")
    assert scan(tmp_path).license_type is None
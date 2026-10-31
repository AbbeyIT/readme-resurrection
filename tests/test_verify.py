from resurrect.scanner import RepoFacts
from resurrect.verify import NEEDS_REVIEW, annotate_doc, verify_doc


def sample_facts():
    return RepoFacts(
        root=".",
        name="demo",
        tree=[
            "src/main.py", "src/a.py", "src/b.py", "src/c.py",
            "requirements.txt", "LICENSE", "tests/test_a.py",
        ],
        dependency_files=["requirements.txt"],
        imports={"src/a.py": ["src/b.py"]},
    )


def found(doc, kind=None):
    issues = verify_doc(doc, sample_facts())
    return {i.text for i in issues if kind is None or i.kind == kind}


def test_paths():
    doc = (
        "Uses `src/main.py` and `src/ghost.py`. See `LICENSE`, `missing.json`, "
        "the `src/` folder, `main.py`, `demo/`, `.venv/` and `and/or`.\n"
    )
    assert found(doc, "path") == {"src/ghost.py", "missing.json"}


def test_commands():
    doc = """Run `pip install -r requirements.txt` or `npm install`.

```bash
pip install -r requirements.txt
npm run build && pip install -r requirements.txt
```

```json
{"scripts": "npm install"}
```
"""
    assert found(doc, "command") == {"npm install", "npm run build"}


def test_import_claims():
    doc = (
        "- `src/a.py` imports `src/b.py`.\n"
        "- `src/a.py` imports `src/b.py` and `src/c.py`.\n"
        "- `src/b.py` imports `src/a.py`.\n"
    )
    assert found(doc, "import") == {"src/a.py -> src/c.py", "src/b.py -> src/a.py"}


def test_annotate_is_idempotent():
    doc = "# Title\n\nRun `npm install`.\n"
    issues = verify_doc(doc, sample_facts())
    once = annotate_doc(doc, issues)
    twice = annotate_doc(once, verify_doc(once, sample_facts()))
    assert once == twice
    assert once.count(NEEDS_REVIEW) == 1
    assert "npm install" in once
    assert NEEDS_REVIEW not in annotate_doc(once, [])
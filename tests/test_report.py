from resurrect.report import (
    age_text, dependency_count, find_existing_docs, revival_score, vitality,
)
from resurrect.scanner import RepoFacts


def test_age_text():
    assert age_text(0) == "0 days"
    assert age_text(1) == "1 day"
    assert age_text(90) == "3 months (90 days)"
    assert age_text(365) == "1 year (365 days)"
    assert age_text(2010) == "5 years, 6 months (2,010 days)"


def test_vitality():
    assert vitality(None) == "unknown"
    assert vitality(179) == "alive"
    assert vitality(180) == "dormant"
    assert vitality(729) == "dormant"
    assert vitality(730) == "dead"


def test_find_existing_docs(tmp_path):
    (tmp_path / "README.md").write_text("x" * 600)
    facts = RepoFacts(
        root=str(tmp_path), name="x", readme_file="README.md",
        tree=["README.md", "docs/ARCHITECTURE.md", "CONTRIBUTING.md", "setup.py", "src/install.py"],
    )
    docs = {d.kind: d for d in find_existing_docs(facts)}
    assert docs["readme"].path == "README.md" and not docs["readme"].stub
    assert docs["architecture"].path == "docs/ARCHITECTURE.md"
    assert docs["contributing"].path == "CONTRIBUTING.md"
    assert docs["setup"].path is None  # setup.py and install.py are code, not documentation
    assert revival_score(list(docs.values())) == 20


def test_stub_readme_counts_as_missing(tmp_path):
    (tmp_path / "README.md").write_text("# hi")
    facts = RepoFacts(root=str(tmp_path), name="x", readme_file="README.md", tree=["README.md"])
    docs = find_existing_docs(facts)
    assert docs[0].stub is True
    assert revival_score(docs) == 100


def test_no_docs_at_all():
    assert revival_score(find_existing_docs(RepoFacts(root=".", name="x"))) == 100


def test_dependency_count():
    facts = RepoFacts(root=".", name="x", dependencies={"a": ["flask", "requests"], "b": ["flask"]})
    assert dependency_count(facts) == 2
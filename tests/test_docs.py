from resurrect.docs import (
    build_facts_block, clean_output, generate_readme, known_commands,
)
from resurrect.gitinfo import GitFacts
from resurrect.scanner import RepoFacts


def sample_facts():
    return RepoFacts(
        root=".", name="demo", file_count=5,
        tree=["main.py", "src/util.py", "requirements.txt", "package.json"],
        languages={"Python": 2},
        dependency_files=["requirements.txt", "package.json"],
        dependencies={"requirements.txt": ["flask", "requests"]},
        entry_points=["main.py"],
        scripts={"start": "node index.js"},
        make_targets=["build"],
        license_file="LICENSE",
    )


def sample_git():
    return GitFacts(is_repo=True, last_commit_date="2020-06-01T12:00:00+00:00",
                    total_commits=12, days_since_last_commit=2000)


def test_known_commands():
    cmds = known_commands(sample_facts())
    assert "pip install -r requirements.txt" in cmds
    assert "npm run start" in cmds
    assert "make build" in cmds
    assert "cargo build" not in cmds
    assert known_commands(RepoFacts(root=".", name="x")) == []
    facts = sample_facts()
    facts.cli_commands = {"demo": "demo.cli:app"}
    assert "demo --help" in known_commands(facts)


def test_facts_block_contents_and_budget():
    summaries = {"main.py": "Starts the app.", "src/util.py": "Helper functions."}
    block = build_facts_block(sample_facts(), sample_git(), summaries)
    assert "Repository name: demo" in block
    assert "flask, requests" in block
    assert "VERIFIED COMMANDS" in block
    assert "- main.py: Starts the app." in block
    small = build_facts_block(sample_facts(), sample_git(), summaries, max_chars=1)
    assert "Helper functions" not in small  # summaries are dropped when over budget


def test_clean_output_strips_fence():
    assert clean_output("```markdown\n# Title\n```") == "# Title\n"
    assert clean_output("# Title") == "# Title\n"


def test_generate_readme_sends_facts_and_rules():
    seen = {}

    def fake_chat(prompt, system=None, config=None, stream=False, on_token=None):
        seen["prompt"], seen["system"] = prompt, system
        return "```\n# demo\n```"

    out = generate_readme(sample_facts(), sample_git(), {"main.py": "Starts the app."},
                          chat_fn=fake_chat)
    assert out == "# demo\n"
    assert "Never invent commands" in seen["system"]
    assert "pip install -r requirements.txt" in seen["prompt"]
    assert "## Installation" in seen["prompt"]

def test_facts_block_license_type():
    facts = sample_facts()
    facts.license_type = "MIT"
    block = build_facts_block(facts, sample_git(), {})
    assert "License file: LICENSE (license type: MIT)" in block
    facts.license_type = None
    block = build_facts_block(facts, sample_git(), {})
    assert "type not detected" in block
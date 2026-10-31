from resurrect.scanner import scan
from resurrect.summarize import read_for_prompt, select_files, summarize_repo


def make_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello world')\n" * 3)
    (tmp_path / "src" / "util.py").write_text("def helper():\n    return 1\n" * 10)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True\n" * 5)
    (tmp_path / "tiny.py").write_text("x=1")
    (tmp_path / "notes.txt").write_text("not code " * 20)
    return tmp_path


def test_select_files_order_and_filters(tmp_path):
    facts = scan(make_repo(tmp_path))
    assert select_files(facts) == ["src/main.py", "src/util.py"]
    assert select_files(facts, max_files=1) == ["src/main.py"]


def test_read_for_prompt_truncates(tmp_path):
    big = tmp_path / "big.py"
    big.write_text("a" * 10000)
    text, truncated = read_for_prompt(big, max_chars=1000)
    assert truncated is True
    assert "omitted" in text
    assert len(text) < 1200
    small, flag = read_for_prompt(make_repo(tmp_path) / "src" / "util.py", max_chars=1000)
    assert flag is False


def test_summarize_repo_uses_cache(tmp_path):
    facts = scan(make_repo(tmp_path))
    cache = tmp_path.parent / "cache-for-test"
    calls = []

    def fake_chat(prompt, system=None, config=None):
        calls.append(prompt)
        return "  A summary.  "

    first = summarize_repo(facts, cache_dir=cache, chat_fn=fake_chat)
    assert first == {"src/main.py": "A summary.", "src/util.py": "A summary."}
    assert len(calls) == 2
    assert "File: src/main.py" in calls[0]

    second = summarize_repo(facts, cache_dir=cache, chat_fn=fake_chat)
    assert second == first
    assert len(calls) == 2  # nothing new was sent to the model
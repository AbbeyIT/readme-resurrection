# Architecture

## Overview
The `readme-resurrection` repository contains a tool designed to "raise dead repos from the grave" by summarizing source code, fetching Git facts, and generating documentation. The tool is built around a command-line interface (CLI) and several supporting modules.

## Directory layout
- `.gitignore`: Specifies intentionally untracked files to ignore.
- `ARCHITECTURE.md`: This document.
- `LICENSE`: Contains the MIT license.
- `README.md`: Project documentation.
- `examples/image.png`: Example image.
- `opencode.json`: Configuration pointing the opencode coding agent at a local Ollama model.
- `pyproject.toml`: Project metadata and dependencies.
- `resurrect/__init__.py`: Initializes the `resurrect` package.
- `resurrect/cli.py`: Main CLI entry point.
- `resurrect/docs.py`: Generates documentation.
- `resurrect/fetch.py`: Clones Git repositories and extracts information.
- `resurrect/gitinfo.py`: Retrieves and processes Git repository information.
- `resurrect/llm.py`: Interacts with a local language model server.
- `resurrect/report.py`: Generates a report on repository documentation and vitality.
- `resurrect/scanner.py`: Analyzes repository to gather facts.
- `resurrect/summarize.py`: Summarizes source code files.
- `resurrect/verify.py`: Verifies generated documentation.
- `tests/test_cli.py`: Tests for the CLI.
- `tests/test_docs.py`: Tests for documentation generation.
- `tests/test_fetch.py`: Tests for fetching Git repositories.
- `tests/test_gitinfo.py`: Tests for Git information retrieval.
- `tests/test_llm.py`: Tests for the language model interaction.
- `tests/test_report.py`: Tests for report generation.
- `tests/test_scanner.py`: Tests for repository scanning.
- `tests/test_summarize.py`: Tests for summarizing source code.
- `tests/test_verify.py`: Tests for verifying documentation.

## Components
- `resurrect/cli.py`: Command-line interface for the tool.
- `resurrect/docs.py`: Generates documentation based on repository facts.
- `resurrect/fetch.py`: Clones Git repositories and extracts information.
- `resurrect/gitinfo.py`: Retrieves and processes Git repository information.
- `resurrect/llm.py`: Interacts with a local language model server.
- `resurrect/report.py`: Generates a report on repository documentation and vitality.
- `resurrect/scanner.py`: Analyzes repository to gather facts.
- `resurrect/summarize.py`: Summarizes source code files.
- `resurrect/verify.py`: Verifies generated documentation.

## How the pieces fit together

- `resurrect/cli.py` imports `resurrect/docs.py`, `resurrect/fetch.py`, `resurrect/gitinfo.py`, `resurrect/llm.py`, `resurrect/report.py`, `resurrect/scanner.py`, `resurrect/summarize.py`, `resurrect/verify.py`.
- `resurrect/docs.py` imports `resurrect/gitinfo.py`, `resurrect/llm.py`, `resurrect/scanner.py`.
- `resurrect/report.py` imports `resurrect/gitinfo.py`, `resurrect/scanner.py`.
- `resurrect/summarize.py` imports `resurrect/llm.py`, `resurrect/scanner.py`.
- `resurrect/verify.py` imports `resurrect/docs.py`, `resurrect/scanner.py`.

## Dependencies
- `typer`
- `rich`
- `httpx`

# Setup

## Prerequisites
- Python >=3.10
- [Ollama](https://ollama.com), running locally, with the default model pulled: `ollama pull qwen2.5-coder:7b` (needed to run the tool, but not for the tests, which use a fake model)
- git (only needed when scanning GitHub URLs)

## Installation
1. Run `pip install .` in the root directory of the repository to install the main package.
2. If you need the development dependencies, run `pip install ".[dev]"` to install `pytest`.

  ## Running
  Run `resurrect --help` to see the options. To preview a report without a model, run `resurrect . --dry-run`.

## Running tests
To run the tests, use the command `python -m pytest` from the root directory of the repository. The tests are located in the `tests` folder.

## Open questions
- None

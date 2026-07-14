# TsFile Python Environment

TsFile 2.3.1 declares `pyarrow >=18,<20`, while patched Arrow begins at 23.0.1. Runtime compatibility is verified by installing the pinned TsFile wheel without its stale Arrow dependency:

```bash
uv pip install --python .venv/bin/python 'pandas==2.2.3'
uv pip install --python .venv/bin/python --no-deps 'tsfile==2.3.1'
```

The shared environment retains `pyarrow==23.0.1`. TsFile results are therefore `ADAPTED`, record this installation mode, and never enter the fair-lane ranking.

Run `uv sync --frozen` to return the virtual environment to the main lock after the experiment.

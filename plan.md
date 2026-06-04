The implementation plan has been written to `docs/plans/2026-06-03-sphinx-api-extraction.md`. It covers 8 ordered steps:

1. **Add sphinx dev dependency** — one line in `pyproject.toml`
2. **Create `docs/source/conf.py`** — minimal Sphinx config with autodoc, napoleon, typehints, and the custom builder extension
3. **Create `docs/source/index.rst`** — automodule directives for all 12 public modules
4. **Implement `docs/_builders/json_api.py`** — the full `JsonApiBuilder` class with neomodel property extraction, relationship extraction, method/signature extraction, and Google-style docstring parsing
5. **Add `docs/_build/` to `.gitignore`**
6. **Upgrade docstrings to Google style** — file-by-file breakdown with specific method lists for all 15 source files
7. **Verify the build** — checklist of 6 assertions to confirm `api_metadata.json` is correct
8. **Run existing tests** — regression check

16 files are touched in total (5 new, 11 modified).
## Summary

<!-- What changed, and why. A few bullets is usually enough. -->

-

## Test plan

<!-- How you verified this. Check what applies, delete what doesn't. -->

- [ ] `uv run pytest -v` passes (default `uv sync`, no extra groups)
- [ ] `uv run mkdocs build --strict` is clean
- [ ] `uv sync --locked` (plain default) still succeeds — the fast path stays untouched

## If this adds or changes a harness

<!-- Delete this section if it doesn't apply. -->

- [ ] Implements only the patterns the framework expresses **natively**; the
      rest are documented as non-fits in the harness's own README (see
      `deepagents_harness/README.md` for the shape).
- [ ] The harness directory name does **not** collide with the framework's
      own top-level import name (e.g. `openai_agents_harness/`, not
      `agents/`) — verify with
      `uv run python -c "import <pkg>; print(<pkg>.__file__)"` and confirm
      it resolves to site-packages, not this repo.
- [ ] Runs fully offline against a stand-in model — a persistent
      `responder` callable inspecting message history, the same shape
      `shared/llm/fake.py`'s `FakeChatModel` and every other harness's fake
      use. A harness that can only talk to a live endpoint belongs in docs,
      not here (see `dapr_agents_harness/README.md` for the one accepted,
      explicitly-documented exception).
- [ ] New/updated dependencies are their own optional `[dependency-groups]`
      entry in `pyproject.toml` (not eager), added to `[tool.uv] conflicts`
      if they're a new framework, and `uv.lock` is regenerated.
- [ ] `pyproject.toml`'s `testpaths` / `[tool.setuptools.packages.find]`
      include the new package.
- [ ] Docs: a one-line `docs/<name>.md` include-markdown shim, an
      `mkdocs.yml` nav entry, and (if relevant) a row in
      `docs/comparison.md`.
- [ ] Root `README.md`: a bullet under "What's here" and an entry in
      "Project layout".
- [ ] `.github/workflows/tests.yml`: a new matrix entry in `pytest-harness`.

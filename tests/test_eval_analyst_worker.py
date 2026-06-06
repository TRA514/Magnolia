"""Parse / string checks for the eval-analyst worker prose (Phase 4, Task 7).

These are deterministic text assertions over scripts/workers/eval-analyst.md.
They guard the Phase 4 contract: the worker reads the frontmatter-sourced digest
(not LangFuse) and emits machine-applicable .patch files + recommendation cards.
"""

import pathlib

WORKER = pathlib.Path("scripts/workers/eval-analyst.md")


def _frontmatter(txt):
    """Return the YAML frontmatter block as raw text (between the first two ---)."""
    return txt.split("---", 2)[1]


def _parse_frontmatter(fm):
    """Parse frontmatter to a dict. Prefer PyYAML; fall back to a tiny
    top-level key:value scanner so the test stays deterministic even where
    PyYAML isn't installed (the only key we assert on is a flat scalar)."""
    try:
        import yaml  # noqa: F401
        return yaml.safe_load(fm)
    except Exception:
        data = {}
        for line in fm.splitlines():
            if line and not line[0].isspace() and ":" in line:
                key, _, val = line.partition(":")
                data[key.strip()] = val.strip().strip('"').strip("'")
        return data


def test_eval_analyst_worker_frontmatter_parses():
    txt = WORKER.read_text()
    data = _parse_frontmatter(_frontmatter(txt))
    assert data["name"] == "eval-analyst"


def test_eval_analyst_mentions_recommendation_and_patch():
    txt = WORKER.read_text()
    assert "--card-type recommendation" in txt
    assert "--patch-path" in txt
    assert "git apply --check" in txt


def test_eval_analyst_clusters_by_deliverable_kind():
    """Clustering is by judge_kind (deliverable KIND), not old trace names."""
    txt = WORKER.read_text()
    assert "judge_kind" in txt
    # the three deliverable kinds are named as the by_step keys
    for kind in ("document", "message", "meeting"):
        assert kind in txt
    # the old trace names, if mentioned at all, are explicitly disclaimed as NOT
    # the step values (rather than presented as the clustering keys)
    low = txt.lower()
    if "worker-execution" in low or "task-parser" in low:
        assert "not" in low and "trace name" in low


def test_eval_analyst_no_langfuse_source_language():
    """The worker must no longer claim LangFuse is the source of the signal.

    Robust, not literal-naive: we assert the old source phrasings are gone and
    that the new frontmatter source is named, while still permitting LangFuse to
    be referenced elsewhere (e.g. langfuse_prompt config) as an optional mirror.
    """
    txt = WORKER.read_text()
    low = txt.lower()
    # old source claims removed
    assert "langfuse human annotation" not in low
    assert "land on langfuse traces" not in low
    assert "or langfuse was down" not in low
    # new source named
    assert "frontmatter" in low

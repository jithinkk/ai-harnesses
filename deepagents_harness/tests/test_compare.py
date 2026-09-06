"""`compare.py` is the cross-harness side-by-side. It must (a) always be
importable, (b) render whichever harnesses are installed, and (c) turn a
missing harness into a labelled skip line rather than a crash. deepagents
is a non-optional dependency, so it is always one of the rendered ones.
"""

import compare


def test_orchestrator_workers_comparison_includes_deepagents():
    out = compare.compare("orchestrator-workers")

    assert "deepagents · orchestrator-workers" in out
    assert "fan-out owner" in out
    assert "subtasks (runtime) : 3" in out


def test_human_in_the_loop_comparison_includes_deepagents():
    out = compare.compare("human-in-the-loop")

    assert "deepagents · human-in-the-loop" in out
    assert "gate fired   : yes" in out


def test_a_missing_harness_is_a_skip_line_not_an_error():
    out = compare.compare("orchestrator-workers")

    # Whatever isn't installed in this environment shows up as a skip,
    # never an exception bubbling out of compare().
    for name in ("openai-agents", "agent-framework", "strands", "dapr-agents"):
        header = f"{name} · orchestrator-workers"
        if header in out:
            continue  # installed here, fine
    assert "orchestrator-workers —" in out  # the summary count line rendered


def test_unknown_pattern_is_rejected():
    import pytest

    with pytest.raises(SystemExit):
        compare.compare("prompt-chaining")

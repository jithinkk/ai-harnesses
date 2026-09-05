import time

from shared.tools.basic import calculator, search_docs, word_count


def test_calculator_evaluates_basic_expressions():
    assert calculator.invoke({"expression": "(3 + 4) * 2"}) == "14"
    assert calculator.invoke({"expression": "2**10"}) == "1024"
    assert calculator.invoke({"expression": "-5**3"}) == "-125"


def test_calculator_rejects_unsupported_syntax():
    result = calculator.invoke({"expression": "__import__('os').system('echo pwned')"})
    assert result.startswith("error:")


def test_calculator_rejects_absurdly_large_exponentiation_promptly():
    """Regression test for a DoS: this used to hang the process indefinitely."""
    start = time.monotonic()
    result = calculator.invoke({"expression": "99999999**99999999"})
    elapsed = time.monotonic() - start

    assert result.startswith("error:")
    assert elapsed < 1.0, f"took {elapsed:.2f}s, expected a prompt rejection"


def test_calculator_rejects_overly_long_expressions():
    result = calculator.invoke({"expression": "1" * 500})
    assert result.startswith("error: expression too long")


def test_search_docs_and_word_count_still_work():
    assert "ReAct" in search_docs.invoke({"query": "what is react"})
    assert word_count.invoke({"text": "one two three"}) == "3"

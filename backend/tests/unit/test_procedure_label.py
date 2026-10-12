"""What the API shows as a procedure: words, never a bare source code."""

import pytest

from dgate.tenders import procedure_label


@pytest.mark.parametrize("raw,shown", [
    ("open", "Open procedure"),
    ("neg-w-call", "Negotiated procedure with prior call for competition"),
    ("Procédure NC", "Procédure NC"), ("ContractNotice", "Contract notice"),
])
def test_words_are_shown(raw, shown):
    assert procedure_label(raw) == shown


@pytest.mark.parametrize("raw", [None, "", "16", "29", "V", "4", "BZP 1.1.1", "BZP 2.1"])
def test_a_bare_code_is_not_shown(raw):
    assert procedure_label(raw) is None

import httpx
import pytest

from dgate import eligibility

PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
       b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 20 100 Td (Hello eligibility) Tj ET\nendstream endobj\n"
       b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\nstartxref\n0\n%%EOF\n")


def _fact(value=None, confidence=0.0, quote=None):
    return {"value": value, "confidence": confidence, "quote": quote}


def _answer(**given):
    return {name: given.get(name, _fact()) for name in eligibility.FIELDS}


def test_a_quote_found_in_the_text_verifies_the_fact_whatever_the_spacing_and_case():
    text = "6. Eligible countries\nLegal entities   established in Member States\nand associated countries."
    out = eligibility.check_quotes(
        _answer(eligible_countries=_fact("EU and associated", 0.9,
                                         "legal entities established in member states and associated countries")), text)
    assert out["eligible_countries"]["verified"] is True
    assert out["eligible_countries"]["confidence"] == 0.9


def test_a_stated_fact_whose_quote_is_not_in_the_text_is_capped_and_not_verified():
    out = eligibility.check_quotes(
        _answer(sme_only=_fact(True, 0.95, "only SMEs may apply")), "Nothing about small firms here.")
    assert out["sme_only"]["verified"] is False
    assert out["sme_only"]["confidence"] == eligibility.UNVERIFIED_CAP
    assert out["sme_only"]["value"] is True, "kept, not erased: the reviewer sees what the model said"


def test_an_unstated_fact_stays_null_and_unverified():
    out = eligibility.check_quotes(_answer(), "text")
    assert all(f["value"] is None and f["verified"] is False for f in out.values())


def test_the_schema_is_closed_so_that_strict_structured_output_accepts_it():
    s = eligibility.schema()

    def objects(node):
        if isinstance(node, dict):
            if "properties" in node:
                yield node
            for v in node.values():
                yield from objects(v)
        elif isinstance(node, list):
            for v in node:
                yield from objects(v)

    found = list(objects(s))
    assert len(found) >= 6
    for o in found:
        assert o["additionalProperties"] is False
        assert set(o["required"]) == set(o["properties"])


def _http(body, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, content=body)))


def test_the_text_of_a_pdf_is_read():
    digest, pages, text = eligibility.fetch_text("https://x.test/a.pdf", _http(PDF))
    assert pages == 1 and "Hello eligibility" in text and len(digest) == 64


def test_something_that_is_not_a_pdf_is_refused():
    with pytest.raises(ValueError, match="not a PDF"):
        eligibility.fetch_text("https://x.test/a.pdf", _http(b"<html>no</html>"))
    with pytest.raises(ValueError, match="HTTP 404"):
        eligibility.fetch_text("https://x.test/a.pdf", _http(b"", 404))

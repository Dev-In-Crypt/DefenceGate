"""WP-100: the supplier's contracts file is priced like the statement it runs; the export reads a publication range."""

from __future__ import annotations

import inspect

from dgate import hardening, tenders


def test_a_suppliers_contracts_file_costs_more_than_its_profile():
    assert hardening.request_cost("/v1/suppliers/12-acme/contracts", {}) == 5
    assert hardening.request_cost("/v1/suppliers/12-acme", {}) == 2


def test_the_export_reads_a_publication_range():
    params = inspect.signature(tenders.export_tenders).parameters
    assert {"publishedFrom", "publishedTo"} <= set(params)

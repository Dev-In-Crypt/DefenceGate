"""WP-94: the cleaner marks Spanish persons by the stated number and a given name, not every capitals-only name."""

from __future__ import annotations

import pytest

from dgate.ops import clean_suppliers, person_preview

from .test_supplier_map import env, put_notice  # noqa: F401  (fixture)

pytestmark = pytest.mark.integration

ROWS = [  # name_as_stated, identifier_as_stated, expected excluded_reason
    ("GABRIELA GARCIA CARRASCAL", None, "person_name"),
    ("DISA GAS S.A.U", None, None),
    ("CONTINENTAL TIRES", None, None),
    ("HIERROS BUENO SAL", None, None),
    ("JUAN GARCIA LOPEZ", "B12345678", None),            # a CIF: an entity, whatever its name
    ("ANY TRADE NAME", "12345678Z", "person_identifier"),  # a DNI
]


def test_the_cleaner_and_the_preview_flag_only_the_persons(conn, env, capsys):  # noqa: F811
    for n, (name, ident, _) in enumerate(ROWS, 1):
        opp = put_notice(conn, f"{n}-2026", country="ES")
        org = conn.execute("INSERT INTO organisation (canonical_name, country) VALUES (%s, 'ES') RETURNING id",
                           (name.lower(),)).fetchone()["id"]
        conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated,
                                           identifier_as_stated, winners_in_notice, cpv_main, resolution_method,
                                           resolution_confidence)
                        VALUES (%s, %s, 'ES', %s, %s, 1, '35400000', 'exact_name', 1.0)""", (opp, org, name, ident))
    conn.commit()

    assert person_preview.main([]) == 0
    out = capsys.readouterr().out
    assert "6 award rows read; 2 would be a natural person" in out and "2 distinct" in out
    assert "GABRIELA" in out and "DISA" not in out
    assert conn.execute("SELECT count(*) AS n FROM award WHERE excluded_reason IS NOT NULL").fetchone()["n"] == 0

    clean_suppliers.run(conn, write=True)
    got = {r["name_as_stated"]: r["excluded_reason"]
           for r in conn.execute("SELECT name_as_stated, excluded_reason FROM award").fetchall()}
    assert got == {name: why for name, _, why in ROWS}

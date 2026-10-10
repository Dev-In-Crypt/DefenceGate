"""The French connector (Agence de l'innovation de defense).

The fixtures are phrases the agency's pages used on 10 October 2026, verbatim where the
phrasing is the point: the dates are prose, in about eight shapes, and no field says
which of them is the closing one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from dgate.normalise import from_aid, strip_personal_data
from dgate.sources import aid


def paris(y, mo, d, h=23, mi=59):
    """A Paris wall-clock time as the UTC instant the connector should produce."""
    from zoneinfo import ZoneInfo
    return datetime(y, mo, d, h, mi, tzinfo=ZoneInfo("Europe/Paris")).astimezone(UTC)


# ------------------------------------------------------------ the dates

@pytest.mark.parametrize("text,published,expected", [
    # labelled, numeric, with a zone name after the time
    ("Ouverture : 16/12/2025 à 09:00 CET Limite de dépôt des projets : 02/03/2026 à 15:00 CET "
     "Informations utiles", date(2026, 1, 12), [paris(2026, 3, 2, 15, 0)]),
    # two limits: both kept, the later one last
    ("Ouverture : 23/12/2025 à 09:00 Limite dépôt dossiers L1 : 16/02/2026 à 15:00 "
     "Limite dépôt dossiers L2 : 25/05/2026 à 15:00 Informations utiles", date(2026, 1, 12),
     [paris(2026, 2, 16, 15, 0), paris(2026, 5, 25, 15, 0)]),
    ("Fermeture : 15/09/2023 à 15h00 Pour en savoir plus", date(2023, 7, 21),
     [paris(2023, 9, 15, 15, 0)]),
    # month written out, date alone
    ("Limite de dépôt des projets : 15 septembre 2026 La proposition devra", date(2026, 6, 8),
     [paris(2026, 9, 15)]),
    # "date de cloture ... avant le", with the weekday and "a minuit"
    ("Date de clôture Les réponses sont attendues avant le vendredi 10 juillet 2026 à minuit .",
     date(2026, 4, 28), [paris(2026, 7, 10)]),
    # a sentence about applying
    ("Le dossier de candidature complet devra être déposé en ligne avant le 20 février 2026 "
     "à 23h59 .", date(2026, 1, 15), [paris(2026, 2, 20, 23, 59)]),
    ("son dossier d’inscription complet avant le mardi 07/08/2026 à 18h CET.", date(2026, 7, 16),
     [paris(2026, 8, 7, 18, 0)]),
    # no year written: the first such date after the page's own publication
    ("Vous avez jusqu’au vendredi 29 mai pour candidater.", date(2026, 3, 17),
     [paris(2026, 5, 29)]),
    ("Vous avez jusqu’au mardi 16 juin pour candidater.", date(2026, 3, 5), [paris(2026, 6, 16)]),
    # a range of dates for applying
    ("Les étapes : -Du 6 janvier au 2 mars : dépôt des candidatures (exclusivement en anglais) ; "
     "-Du 3 mars au 31 mars : examen des dossiers", date(2026, 1, 14), [paris(2026, 3, 2)]),
    # a challenge's applications phase wins over the "date limite" of its later step
    ("Étape 1 - Phase d'appel à candidatures : du 20/07/2026 au 18/09/2026 Étape 2 - Date "
     "limite de remise du dossier de présentation du projet : 27/10/2026 Essais de "
     "calibration : du 16/11/2026 au 20/11/2026", date(2026, 7, 22), [paris(2026, 9, 18)]),
    # "pour le", a two-digit year and a zone in brackets
    ("Les propositions de réponse à cet appel à projets sont attendues pour le 26/11/2025 à "
     "23H59 en remplissant le formulaire", date(2025, 10, 1), [paris(2025, 11, 26, 23, 59)]),
    ("Date d’ouverture de l’appel d’offre : 27/11/25 Date de fermeture de l’appel d’offre : "
     "02/02/26 à 16H00 (UTC+1) Méthode d’attribution", date(2025, 12, 15),
     [paris(2026, 2, 2, 16, 0)]),
])
def test_the_closing_date_is_read_in_each_phrasing_the_agency_uses(text, published, expected):
    assert aid.deadlines(text, published) == expected


def test_a_webinar_registration_date_is_not_the_deadline():
    text = ("Date de clôture Les réponses sont attendues avant le vendredi 10 juillet 2026 à "
            "minuit . Un webinaire d’information est prévu le mardi 12 mai de 14h30 à 16h30, "
            "sur inscription avant le mercredi 6 mai à l’adresse mail : x.")
    assert aid.deadlines(text, date(2026, 4, 28)) == [paris(2026, 7, 10)]


def test_a_year_less_date_rolls_to_next_year_when_it_has_already_passed_the_publication():
    # Published in November, "jusqu'au 15 janvier": January of the following year.
    got = aid.deadlines("Vous avez jusqu’au jeudi 15 janvier pour candidater.", date(2026, 11, 3))
    assert got == [paris(2027, 1, 15)]


def test_a_page_with_no_date_has_none_and_is_not_given_one():
    text = ("Si vous avez un projet en cyber sécurité qui peut intéresser la défense, vous "
            "pouvez déposer un dossier pour avoir accès à la Cyber Defense Factory.")
    assert aid.deadlines(text, date(2026, 2, 5)) == []


def test_the_opening_date_is_read():
    assert aid.opening("Ouverture : 16/12/2025 à 09:00 CET Limite de dépôt") == date(2025, 12, 16)
    assert aid.opening("rien") is None


# --------------------------------------------------------------- status

def _record(text="", *, listed="cours", published="2026-03-17"):
    return {"slug": "x", "title": "Défi", "list": listed, "published": published, "text": text}


NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def test_the_status_follows_the_date_not_the_lists_label():
    """"En cours" held a call whose deadline was 15 January 2026 on 10 October."""
    stale = _record("Date de clôture Les réponses sont attendues avant le 15 janvier 2026 à minuit.",
                    listed="cours")
    assert aid.status(stale, now=NOW) == "closed"
    live = _record("Limite de dépôt des projets : 15 décembre 2026", listed="cours")
    assert aid.status(live, now=NOW) == "open"


def test_a_call_not_yet_open_is_forthcoming():
    text = "Ouverture : 20/11/2026 à 09:00 Limite de dépôt des projets : 15/01/2027 à 15:00"
    assert aid.status(_record(text), now=NOW) == "forthcoming"


def test_a_page_without_a_date_takes_its_lists_word():
    assert aid.status(_record("", listed="cours"), now=NOW) == "open"
    assert aid.status(_record("", listed="clotures"), now=NOW) == "closed"
    assert aid.status(_record("", listed="standing"), now=NOW) == "open"


def test_a_closed_call_of_an_earlier_year_is_out_and_this_years_is_in():
    old = _record("Fermeture : 15/09/2023 à 15h00", listed="clotures", published="2023-07-21")
    assert not aid.in_scope(old, today=date(2026, 10, 10))
    this_year = _record("Fermeture : 15/03/2026 à 15h00", listed="clotures", published="2026-01-10")
    assert aid.in_scope(this_year, today=date(2026, 10, 10))
    undated_old = _record("", listed="clotures", published="2025-02-05")
    assert not aid.in_scope(undated_old, today=date(2026, 10, 10))
    standing = _record("Appel à projets permanent", listed="standing", published="2024-01-01")
    assert aid.in_scope(standing, today=date(2026, 10, 10))


# ----------------------------------------------------------- the pages

PAGE = """<html><head>
<meta property="og:title" content="ASTRID 2026 : Accompagnement Spécifique des Travaux" />
<meta property="og:description" content="L&#039;AID lance l&#039;édition 2026 de l&#039;appel ASTRID." />
<meta property="article:published_time" content="2026-01-12T10:00:00+0100" />
<meta property="article:modified_time" content="2026-01-13T10:00:00+0100" />
</head><body><header>menu</header><main><h1>ASTRID 2026</h1>
<p>Le montant maximum de l'aide allouée est limité à 400 k€.</p>
<p>Ouverture : 16/12/2025 à 09:00 CET Limite de dépôt des projets : 02/03/2026 à 15:00 CET</p>
<p>Contact : jean.dupont@defense.gouv.fr</p>
<p>Partager la page Veuillez autoriser le dépôt de cookies A la une 8 octobre 2026
Limite de dépôt des projets : 01/01/2027</p></main></body></html>"""


class _Client:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, timeout=None):
        path = url.replace(aid.SITE, "")

        class _R:
            text = self.pages[path]

            def raise_for_status(self):
                pass
        return _R()


def test_a_page_ends_where_the_sharing_block_begins():
    """After "Partager la page" comes a carousel of other news, with dates of its own
    that change every day. Read, it would give a wrong deadline and a new hash nightly."""
    record = aid.fetch_page(_Client({"/aid/appels-projets/cours/astrid": PAGE}), "cours",
                            "/aid/appels-projets/cours/astrid")
    assert "2027" not in record["text"] and "A la une" not in record["text"]
    assert aid.deadlines(record["text"], date(2026, 1, 12)) == [paris(2026, 3, 2, 15, 0)]
    assert record["slug"] == "astrid"
    assert record["published"] == "2026-01-12" and record["summary"].startswith("L'AID lance")


def test_a_list_with_no_call_links_is_an_error_not_an_empty_list():
    client = _Client({aid.LISTS["cours"]: "<main>rien</main>", aid.LISTS["clotures"]: "<main/>"})
    with pytest.raises(RuntimeError, match="page changed shape"):
        aid.list_pages(client)


def test_the_slug_identifies_a_call_across_the_two_lists():
    """A call moves from "cours" to "clotures" and its path moves with it."""
    a = aid.fetch_page(_Client({"/aid/appels-projets/cours/astrid": PAGE}), "cours",
                       "/aid/appels-projets/cours/astrid")
    b = aid.fetch_page(_Client({"/aid/appels-projets/clotures/astrid": PAGE}), "clotures",
                       "/aid/appels-projets/clotures/astrid")
    assert a["slug"] == b["slug"] == "astrid"


# ------------------------------------------------------------- mapping

def test_a_page_maps_completely():
    record = aid.fetch_page(_Client({"/aid/appels-projets/cours/astrid": PAGE}), "cours",
                            "/aid/appels-projets/cours/astrid")
    call = from_aid(record, today=date(2026, 2, 1))
    assert (call.programme_code, call.native_id, call.country, call.regime) == \
        ("FR-AID", "astrid", "FR", "defence")
    assert call.title.startswith("ASTRID 2026")
    assert call.type_of_action == "research grant"
    assert call.opens_at == date(2025, 12, 16)
    assert call.deadline_at == paris(2026, 3, 2, 15, 0)
    assert call.status == "open"
    assert call.budget is None                      # 400 k€ is a ceiling per project
    assert call.conditions_raw["max_aid_eur_per_project"] == 400_000
    assert call.source_url.endswith("/aid/appels-projets/cours/astrid")


@pytest.mark.parametrize("title,kind", [
    ("ASMA 2026 : Accompagnement Spécifique", "research grant"),
    ("Participez au Défi Cyber « Détection de fake vidéo »", "challenge"),
    ("Appel à Manifestation d’Intérêt n°3", "expression of interest"),
    ("Appel à projet pour la « Cyber Defense Factory »", "call for projects"),
    ("RAPID (Régime d’APpui à l’Innovation Duale)", "innovation grant (RAPID)"),
    ("BraveTech EU", None),
])
def test_the_kind_of_call_comes_from_its_title(title, kind):
    assert aid.kind_of(title) == kind


def test_an_address_in_the_page_is_removed_before_landing():
    record = aid.fetch_page(_Client({"/aid/appels-projets/cours/astrid": PAGE}), "cours",
                            "/aid/appels-projets/cours/astrid")
    assert "jean.dupont@defense.gouv.fr" not in strip_personal_data(record)["text"]


def test_a_page_with_no_title_is_refused():
    with pytest.raises(ValueError, match="no title"):
        aid.fetch_page(_Client({"/x": "<main>rien</main>"}), "cours", "/x")

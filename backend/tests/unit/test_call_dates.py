"""Call dates: a day with no time closes at the end of that day, and says it is a date.

Shapes are the ones the sources returned on 12 October 2026: the EU portal states every
deadline as midnight UTC (155 of 155), NCBR writes `T00:00:00` on 15 of 68 competitions
and was read as 00:00 Warsaw, a day early, and the portals carry a publication date the
connectors did not map (177 of 189 calls had none).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from dgate.normalise import from_aid, from_bdns, from_eu_call, from_ncbr
from dgate.sources import aid, ncbr
from dgate.sources import eu_portal as portal

SEP_29 = "1790640000000"            # 2026-09-29 00:00:00 UTC
DEC_01 = "1796083200000"            # 2026-12-01 00:00:00 UTC
NOON_SEP_29 = str(int(SEP_29) + 12 * 3600 * 1000)


def _topic(**over):
    record = {
        "type": 1, "ccm2Id": 45095551, "identifier": "EDF-2026-RA-SENS-MSDT",
        "callIdentifier": "EDF-2026-RA", "title": "Multidomain sensors demonstrator",
        "frameworkProgramme": [{"abbreviation": "EDF"}], "programmeDivision": [],
        "status": {"abbreviation": "Open"}, "tags": [],
        "publicationDateLong": 1770768000000,                   # 2026-02-11
        "actions": [{"types": [{"typeOfAction": "EDF-RA"}], "deadlineDates": [SEP_29]}],
    }
    record.update(over)
    return record


# ---------------------------------------------------------------- EU portal

def test_a_portal_deadline_at_midnight_closes_at_the_end_of_that_day_in_brussels():
    record = _topic()
    assert portal.closing_is_date(record)
    assert portal.closing(record) == datetime(2026, 9, 29, 21, 59, 59, tzinfo=UTC)     # CEST
    winter = _topic(actions=[{"deadlineDates": [DEC_01]}])
    assert portal.closing(winter) == datetime(2026, 12, 1, 22, 59, 59, tzinfo=UTC)     # CET


def test_the_end_of_day_is_still_the_stated_day_in_utc_so_the_site_prints_it_right():
    assert portal.closing(_topic()).date() == date(2026, 9, 29)


def test_a_deadline_that_carries_a_time_is_kept_as_the_instant():
    record = _topic(actions=[{"deadlineDates": [NOON_SEP_29]}])
    assert not portal.closing_is_date(record)
    assert portal.closing(record) == datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def test_the_first_cut_off_stays_the_deadline_unless_the_call_has_several():
    two_stage = _topic(actions=[{"deadlineDates": [SEP_29, DEC_01]}])
    now = datetime(2026, 10, 12, tzinfo=UTC)
    assert portal.closing(two_stage, now=now).date() == date(2026, 9, 29)


def test_a_multiple_cut_off_call_shows_the_next_cut_off_still_to_come():
    several = _topic(deadlineModel={"abbreviation": "multiple cut-off"},
                     actions=[{"deadlineDates": [SEP_29, DEC_01]}])
    assert portal.closing(several, now=datetime(2026, 10, 12, tzinfo=UTC)).date() == date(2026, 12, 1)
    assert portal.closing(several, now=datetime(2026, 9, 1, tzinfo=UTC)).date() == date(2026, 9, 29)
    assert portal.closing(several, now=datetime(2027, 1, 1, tzinfo=UTC)).date() == date(2026, 12, 1)


def test_a_call_with_no_deadline_has_no_closing_and_no_date_flag():
    record = _topic(actions=[])
    assert portal.closing(record) is None and not portal.closing_is_date(record)


def test_the_publication_date_is_mapped_from_the_portals_epoch():
    call = from_eu_call(_topic())
    assert call.published_at == date(2026, 2, 11)
    assert call.deadline_precision == "date"
    assert from_eu_call(_topic(publicationDateLong=None)).published_at is None


# ------------------------------------------------------------ military mobility

CEF_MILMOB = {
    "type": 1, "ccm2Id": 51468068, "identifier": "CEF-T-2026-MILMOB-WORKS",
    "callIdentifier": "CEF-T-2026-MILMOB",
    "title": "Adaptation of the TEN-T to civilian-defence dual use - studies, works or mixed",
    "frameworkProgramme": {"id": 43251567, "abbreviation": "CEF2027",
                           "description": "Connecting Europe Facility (CEF)"},
    "programmeDivision": [{"id": 45101675, "abbreviation": "CEF-2.1.3",
                           "description": "Military Mobility"}],
    "status": {"id": 31094503, "abbreviation": "Closed"},
    "tags": ["CEF", "MILMOB", "military mobility"],
    "publicationDateLong": 1781740800000,
    "actions": [{"deadlineDates": ["1791244800000"]}],           # 2026-10-06
}


def test_the_cef_military_mobility_topic_is_in_scope_as_dual_use():
    assert portal.regime(CEF_MILMOB) == "dual_use"
    assert portal.in_scope(CEF_MILMOB, today=date(2026, 10, 12)) is True
    assert from_eu_call(CEF_MILMOB).programme_code == "CEF2027"


def test_a_cef_topic_that_is_not_military_mobility_stays_out():
    other = {**CEF_MILMOB, "identifier": "CEF-T-2026-GREEN-WORKS", "tags": ["CEF"],
             "programmeDivision": [{"abbreviation": "CEF-2.1.1", "description": "Sustainable"}]}
    assert portal.regime(other) is None
    assert portal.in_scope(other, today=date(2026, 10, 12)) is False


def test_an_old_military_mobility_call_is_not_collected_with_this_years():
    old = {**CEF_MILMOB, "ccm2Id": 44315474, "identifier": "CEF-T-2021-MILMOB-WORKS",
           "actions": [{"deadlineDates": ["1635984000000"]}]}          # 2021-11-04
    assert portal.in_scope(old, today=date(2026, 10, 12)) is False


# --------------------------------------------------------------------- NCBR

def _ncbr(**over):
    record = {
        "name": "FENG.01.01-IP.01-003/26 - Sciezka SMART", "path": "/web/ncbr/feng-smart",
        "publishDate": "2026-08-21T14:22:34.0542", "announcementDate": "2026-07-01T00:00:00",
        "applicationsStartDate": "2026-07-01T09:00:00",
        "applicationsEndDate": "2026-10-16T00:00:00",
        "status": "APPLICATIONS_IN_PROGRESS", "budget": "350 000 000 zł",
        "typesOfApplicant": '["large_enterprise"]', "thematicAreas": '["defence_and_security"]',
        "programmeTypes": '["eu"]',
    }
    record.update(over)
    return record


def test_an_ncbr_date_with_no_hour_closes_at_the_end_of_that_day_in_warsaw():
    record = _ncbr()
    assert ncbr.deadline_is_date(record)
    assert ncbr.deadline(record) == datetime(2026, 10, 16, 21, 59, 59, tzinfo=UTC)    # CEST
    assert ncbr.deadline(_ncbr(applicationsEndDate="2026-12-22T00:00:00")) == \
        datetime(2026, 12, 22, 22, 59, 59, tzinfo=UTC)                                 # CET


def test_an_ncbr_deadline_with_an_hour_is_unchanged():
    record = _ncbr(applicationsEndDate="2026-10-16T16:00:00")
    assert not ncbr.deadline_is_date(record)
    assert ncbr.deadline(record) == datetime(2026, 10, 16, 14, 0, tzinfo=UTC)


def test_an_ncbr_call_maps_its_announcement_date_and_has_no_invented_code():
    call = from_ncbr(_ncbr(), today=date(2026, 10, 12))
    assert call.published_at == date(2026, 7, 1)          # the announcement, not the page edit
    assert call.topic_code is None                         # the register has no code field
    assert call.deadline_precision == "date"
    assert call.deadline_at == datetime(2026, 10, 16, 21, 59, 59, tzinfo=UTC)


def test_the_page_edit_date_is_only_the_fallback_publication_date():
    assert ncbr.published_at(_ncbr(announcementDate=None)) == date(2026, 8, 21)
    assert ncbr.published_at(_ncbr(announcementDate=None, publishDate=None)) is None


# ---------------------------------------------------------------------- AID

def test_an_aid_date_with_no_hour_is_flagged_and_one_with_an_hour_is_not():
    day_only = aid.deadlines("Fermeture : 15/03/2026", date(2026, 1, 10))
    hour = aid.deadlines("Fermeture : 15/03/2026 à 15h00", date(2026, 1, 10))
    assert aid.is_end_of_day(day_only[-1])
    assert not aid.is_end_of_day(hour[-1])


def _aid(text, published="2026-01-10"):
    return {"slug": "defi", "title": "Défi", "list": "cours", "published": published,
            "text": text}


def test_an_aid_call_maps_its_page_date_and_its_precision():
    day_only = from_aid(_aid("Fermeture : 15/03/2026"), today=date(2026, 2, 1))
    assert (day_only.published_at, day_only.deadline_precision) == (date(2026, 1, 10), "date")
    timed = from_aid(_aid("Fermeture : 15/03/2026 à 15h00"), today=date(2026, 2, 1))
    assert timed.deadline_precision is None
    standing = from_aid(_aid("Appel à projets permanent"), today=date(2026, 2, 1))
    assert standing.deadline_at is None and standing.deadline_precision is None


# --------------------------------------------------------------------- BDNS

def test_a_bdns_call_is_a_date_with_the_end_of_the_day_already_stored():
    detail = {"codigoBDNS": "912587", "descripcion": "Convocatoria", "abierto": True,
              "fechaFinSolicitud": "2026-11-30", "fechaRecepcion": "2026-10-01",
              "tipoConvocatoria": "Concurrencia competitiva", "organo": {"nivel2": "MINISTERIO"}}
    call = from_bdns(detail, today=date(2026, 10, 12))
    assert call.deadline_precision == "date"
    assert call.deadline_at == datetime(2026, 11, 30, 22, 59, 59, tzinfo=UTC)
    assert call.published_at == date(2026, 10, 1)

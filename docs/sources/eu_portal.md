# EU Funding & Tenders Portal (`eu_portal`): what the source gives for eligibility, documents and time

Read from stored topic documents (raw store, `eu_portal/2026/09/24/run-topics-0004`, one EDF/EDIP topic, one Digital
Europe, one Horizon JU, one Horizon CL3) on 16 October 2026. Connector: `backend/dgate/sources/eu_portal.py`.

**Who can apply.** The topic document has no structured field for eligible countries or organisation types. Its
`conditions` block is HTML with numbered headings; "2. Eligible countries" and "3. Other eligibility conditions" are
references: EDF and Digital Europe say "described in section 6 of the call document", Horizon says "described in Annex B
of the Work Programme General Annexes". Some Horizon topics add criteria in section 3 (CL3: at least two police
authorities from two Member States or Associated Countries). So the answer we can give is the source's own sentence for
those two sections (`funding.who_can_apply`, from the flattened `eligibility_text`, served only where the source's
`commercial_ok` is true) plus the link to the document it names. Nothing is inferred.

**Official documents.** The same block links the call document (`.../docs/2021-2027/<programme>/wp-call/...pdf`), the
application form templates, the model grant agreement and the work programme. `eu_portal.call_documents` keeps those
links (https, `europa.eu` hosts, each once, the source's anchor text as label) in `conditions_raw.documents`; stored
calls are filled by `python -m dgate.ops.call_documents --yes` (raw store only, no request).

**Time of the deadline.** The reference data and the topic document give the deadline as epoch milliseconds at
00:00:00 UTC (a day, no time) whatever the call document sets (155 of 155 on 12 October 2026). The source does not state
a time zone or "end of day". We store the end of that day in Brussels so a call stays open through its last day; that is
our convention, not the source's statement, so the site says "date only" and "time not published by the source", never
"end of day, Brussels".

**Funder and programme.** `frameworkProgramme.description` carries the programme in full ("European Defence Fund (EDF)",
"Horizon Europe (HORIZON)"); the call has no separate funder field. The portal is the Commission's, so an EU call's
funder is served as "European Commission" (`funding.EU_FUNDER`). A Horizon joint-undertaking topic
(`HORIZON-JU-...`) is also served under the Commission: the document names no other body.

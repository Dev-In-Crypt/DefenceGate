"""WP-115: the merge queue skips organisations nothing references. Tests of the merge rules that build bare
organisation rows give each one a project participation: a link that moves nothing those tests read (no notice,
so whether the row publishes notices, which the public-body rule reads, stays; no archive version; no alias)."""

from __future__ import annotations


def link(conn, org_id: int) -> None:
    """Give `org_id` one participation in a shared placeholder project."""
    row = conn.execute("SELECT id FROM project WHERE native_id = 'wp115-link'").fetchone()
    if row is None:
        row = conn.execute(
            """INSERT INTO project (source_id, programme_id, native_id, title, call_year)
               VALUES ((SELECT id FROM source WHERE code = 'cordis'), (SELECT id FROM programme WHERE code = 'EDF'),
                       'wp115-link', 'link', 2024) RETURNING id""").fetchone()
    conn.execute(
        """INSERT INTO participation (project_id, organisation_id, role, resolution_method, resolution_confidence)
           VALUES (%s, %s, 'participant', 'pic', 1) ON CONFLICT DO NOTHING""", (row["id"], org_id))

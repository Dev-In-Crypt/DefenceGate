-- Read side of the tenders list (verification of 13 October 2026, package WP-4).
--
-- `dgate_superseded`: a notice that states no deadline is not served as open when its
-- procedure is over: the TED notice it was forwarded as is awarded, cancelled, closed or
-- past its deadline; another notice of the same procedure is an award or a cancellation
-- published on or after it; or a rectificatif names it (`related_native_id`). 110 of the 129
-- French notices served open on 13 October 2026 were of the first kind.
--
-- A function, not three EXISTS written into the status expression: the expression is part
-- of every filter of the tenders list, and with the subqueries in it the planner priced
-- every row at the cost of three index lookups and chose a plan 40 times slower (0.4 s to
-- 23 s on production data). Declared cheap, it is called only for the few hundred rows
-- that are stored open with no deadline, which is what the CASE reaches it for.
--
-- Reads only; creates and changes no row. Idempotent.
CREATE OR REPLACE FUNCTION dgate_superseded(
    p_id bigint, p_source_id integer, p_native_id text, p_ted_ref text,
    p_procedure_identifier text, p_published_at date)
RETURNS boolean
LANGUAGE sql STABLE PARALLEL SAFE COST 1
AS $$
    SELECT EXISTS (SELECT 1 FROM opportunity tw
                    WHERE tw.source_id = (SELECT id FROM source WHERE code = 'ted')
                      AND tw.native_id = p_ted_ref AND tw.id <> p_id
                      AND (tw.status IN ('awarded', 'cancelled', 'closed')
                           OR (tw.status = 'open' AND tw.deadline_at < now())))
        OR EXISTS (SELECT 1 FROM opportunity sb
                    WHERE sb.procedure_identifier = p_procedure_identifier AND sb.id <> p_id
                      AND sb.status IN ('awarded', 'cancelled')
                      AND sb.published_at >= p_published_at)
        OR EXISTS (SELECT 1 FROM opportunity rc
                    WHERE rc.source_id = p_source_id AND rc.related_native_id = p_native_id
                      AND rc.id <> p_id)
$$;

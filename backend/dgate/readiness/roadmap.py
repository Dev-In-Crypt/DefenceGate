"""The roadmap: what to obtain, in what order, at what cost and in what time, issued by whom.

A pure function of the assessments (`engine.assess`), the company's statuses and the content.
Nothing is estimated here beyond what the sources state:

  * a step is a requirement that an assessed rule says is missing, plus the prerequisites that
    must come first; a requirement the company holds, or has marked not applicable, is not a step;
  * the order is the prerequisite graph (level by level), then cost, then duration, then code;
  * a cost or duration a source does not state is `null`, listed under `unknownCost` and
    `unknownDuration`, never replaced by a guess;
  * totals are ranges, one per currency (money is never converted);
  * steps that depend on nothing in common run in parallel: they are separate tracks, and the
    total time is that of the slowest track;
  * the ISO 9001 branch: the AQAP 2110 step uses the cost and time the source gives for a firm
    that already holds ISO 9001 when the company marks ISO 9001 as held;
  * a requirement whose issuer in the company's country is the state itself (Spain's PECAL route)
    has no price: the vendor ranges of the sources do not describe it.

`call_timing` answers the cross-layer question "this call closes in N weeks: can I realistically
take part, and if not, what is the fastest path?".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .content import Content, Money, Requirement, Span
from .engine import Assessment, RuleResult

DONE = ("held", "not_applicable")
VENDOR_LABEL = "vendor range, not a benchmark"


def _money(m: Money | None) -> dict[str, Any] | None:
    if m is None:
        return None
    return {"min": m.min, "max": m.max, "currency": m.currency, "basis": m.basis, "text": m.text, "alt": m.alt,
            "label": VENDOR_LABEL if m.basis == "vendor_range" else None}


def _span(s: Span | None) -> dict[str, Any] | None:
    return None if s is None else {"min": s.min, "max": s.max, "text": s.text, "note": s.note}


@dataclass
class _Node:
    req: Requirement
    status: str
    cost: Money | None
    days: Span | None
    variant_used: str | None
    blocking_for: list[str]
    needed_for: list[dict[str, str]]
    optional: bool
    level: int = 0
    state_route: bool = False


def _pick(req: Requirement, statuses: Mapping[str, str]) -> tuple[Money | None, Span | None, str | None]:
    for v in req.variants:
        if statuses.get(v.when_held) == "held":
            return v.cost or req.cost, v.days or req.days, v.when_held
    return req.cost, req.days, None


def _state_route(content: Content, code: str, country: str | None) -> bool:
    """Whether the only issuers collected for this country are the state itself: then the vendor price
    ranges of the sources (quotes of commercial certification bodies) say nothing about the cost."""
    rows = [i for i in content.requirements[code].issuers if country and i.country == country]
    return bool(rows) and all(i.state_route for i in rows)


def build_roadmap(assessments: Sequence[Assessment], statuses: Mapping[str, str], content: Content,
                  country: str | None) -> dict[str, Any]:
    nodes: dict[str, _Node] = {}

    def make(req: Requirement, status: str, optional: bool) -> _Node:
        cost, days, used = _pick(req, statuses)
        state = _state_route(content, req.code, country)
        if state:
            cost, days, used = None, None, None
        return _Node(req, status, cost, days, used, [], [], optional, state_route=state)

    def need(code: str, *, optional: bool, programme: str, result: RuleResult) -> None:
        req = content.requirements[code]
        status = statuses.get(code, "not_held")
        if status in DONE:
            return
        node = nodes.get(code)
        if node is None:
            node = nodes[code] = make(req, status, optional)
        node.optional = node.optional and optional
        if result.obligation == "mandatory" and not optional and programme not in node.blocking_for:
            node.blocking_for.append(programme)
        node.needed_for.append({"programme": programme, "rule": result.rule, "title": result.title})

    for a in assessments:
        for r in a.rules:
            if r.requirement is None:
                continue
            if r.outcome in ("not_met", "to_obtain"):
                need(r.requirement, optional=False, programme=a.programme, result=r)
            elif r.outcome == "info":
                need(r.requirement, optional=True, programme=a.programme, result=r)

    # Prerequisites that must come first pull their own steps in (ISO 9001 before AQAP 2110).
    # 'before_or_with' only orders steps that are there anyway: REOCE is not asked of a firm
    # that is not Spanish just because the export licence needs it in Spain.
    pending = list(nodes)
    while pending:
        code = pending.pop()
        for pre, relation in nodes[code].req.prerequisites:
            if relation != "before" or statuses.get(pre, "not_held") in DONE:
                continue
            if pre not in nodes:
                nodes[pre] = make(content.requirements[pre], statuses.get(pre, "not_held"), nodes[code].optional)
                pending.append(pre)
            elif not nodes[code].optional:
                nodes[pre].optional = False
            nodes[pre].needed_for.append({"programme": "", "rule": "", "title": f"Comes before {nodes[code].req.name}"})

    edges: list[tuple[str, str, str]] = []          # (prerequisite, requirement, relation)
    for code, node in nodes.items():
        for pre, relation in node.req.prerequisites:
            if pre in nodes:
                edges.append((pre, code, relation))

    _levels(nodes, edges)
    # What is required first, then what only a contract might ask for; inside each, the graph's level,
    # then the cheaper and the quicker; a step with no stated cost or time comes after one that has.
    ordered = sorted(nodes.values(), key=lambda n: (
        n.optional,
        n.level,
        n.cost.min if n.cost and n.cost.min is not None else float("inf"),
        n.days.min if n.days and n.days.min is not None else float("inf"),
        n.req.code))
    position = {n.req.code: i + 1 for i, n in enumerate(ordered)}
    tracks = _tracks(nodes, edges, position)
    steps = [_step(n, position, content, country, statuses, edges) for n in ordered]

    required = [n for n in ordered if not n.optional]
    return {
        "steps": steps,
        "tracks": tracks,
        "totals": _totals(required, edges),
        "totalsWithOptional": _totals(ordered, edges),
        "unknownCost": [n.req.code for n in required if _unknown_cost(n)],
        "unknownDuration": [n.req.code for n in required if _unknown_days(n)],
        # the same for the total that includes what only a contract might ask for (ISO 9001, with no stated cost)
        "unknownCostWithOptional": [n.req.code for n in ordered if _unknown_cost(n)],
        "unknownDurationWithOptional": [n.req.code for n in ordered if _unknown_days(n)],
        # what a source says is on top of a range but gives no base for: shown, never added to a total
        "notAdded": [{"code": n.req.code, "text": note} for n in ordered if (note := _not_added(n, statuses))],
        "label": VENDOR_LABEL,
    }


def _not_added(n: _Node, statuses: Mapping[str, str]) -> str | None:
    extra = n.req.extras.get("without_prerequisite")
    if n.state_route or n.variant_used or not extra or statuses.get(extra["requirement"], "not_held") in DONE:
        return None
    return extra["text"]


def _unknown_cost(n: _Node) -> bool:
    return n.cost is None or n.cost.min is None or n.cost.max is None


def _unknown_days(n: _Node) -> bool:
    return n.days is None or n.days.min is None or n.days.max is None


def _levels(nodes: dict[str, _Node], edges: list[tuple[str, str, str]]) -> None:
    """Depth in the prerequisite graph: 0 for a step with no prerequisite among the steps."""
    changed = True
    while changed:
        changed = False
        for pre, code, _ in edges:
            if nodes[code].level < nodes[pre].level + 1:
                nodes[code].level = nodes[pre].level + 1
                changed = True


def _tracks(nodes: dict[str, _Node], edges: list[tuple[str, str, str]], position: dict[str, int]) -> list[list[str]]:
    """Connected groups of steps: what depends on each other is one track, the rest run in parallel."""
    group = {code: code for code in nodes}

    def find(x: str) -> str:
        while group[x] != x:
            group[x] = group[group[x]]
            x = group[x]
        return x

    for pre, code, _ in edges:
        group[find(pre)] = find(code)
    out: dict[str, list[str]] = {}
    for code in nodes:
        out.setdefault(find(code), []).append(code)
    tracks = [sorted(codes, key=lambda c: position[c]) for codes in out.values()]
    return sorted(tracks, key=lambda t: position[t[0]])


def _totals(selected: list[_Node], edges: list[tuple[str, str, str]]) -> dict[str, Any]:
    chosen = {n.req.code for n in selected}
    money: dict[str, dict[str, Any]] = {}
    free = []
    for n in selected:
        c = n.cost
        if c is None or c.min is None or c.max is None:
            continue
        if c.currency is None:
            free.append(n.req.code)
            continue
        entry = money.setdefault(c.currency, {"currency": c.currency, "min": 0, "max": 0, "steps": []})
        entry["min"] += c.min
        entry["max"] += c.max
        entry["steps"].append(n.req.code)
    # Duration of the selected steps alone: their own prerequisites among them.
    own_edges = [(p, c, r) for p, c, r in edges if p in chosen and c in chosen]
    finish: dict[str, tuple[int, int]] = {}
    for n in sorted(selected, key=lambda x: x.level):
        starts = [finish[p] for p, c, r in own_edges if c == n.req.code and r == "before"]
        start = (max((s[0] for s in starts), default=0), max((s[1] for s in starts), default=0))
        d = n.days
        finish[n.req.code] = (start[0] + ((d.min or 0) if d else 0), start[1] + ((d.max or 0) if d else 0))
    days = {"min": max((f[0] for f in finish.values()), default=0), "max": max((f[1] for f in finish.values()), default=0)}
    return {"cost": sorted(money.values(), key=lambda m: m["currency"]), "freeSteps": free, "days": days}


def _step(n: _Node, position: dict[str, int], content: Content, country: str | None,
          statuses: Mapping[str, str], edges: list[tuple[str, str, str]]) -> dict[str, Any]:
    req = n.req
    issuers = content.issuers_for(req.code, country)
    prerequisites = []
    for pre, relation in req.prerequisites:
        if relation != "before" and pre not in position:
            continue
        status = statuses.get(pre, "not_held")
        prerequisites.append({"code": pre, "name": content.requirements[pre].name, "relation": relation,
                              "status": status, "step": position.get(pre)})
    parallel_with = sorted(position[c] for c in position
                           if c != req.code and not _related(req.code, c, edges))
    return {
        "order": position[req.code], "code": req.code, "name": req.name, "category": req.category,
        "summary": req.summary, "status": n.status, "optional": n.optional,
        "when": "when a contract names it" if n.optional else None,
        "blockingFor": sorted(n.blocking_for), "neededFor": n.needed_for,
        "cost": _money(n.cost), "days": _span(n.days), "variantUsed": n.variant_used,
        "branchNote": _branch_note(req, n, statuses, content),
        "issuers": [{"country": i.country, "name": i.name, "url": i.url, "notes": i.notes,
                     "status": i.status} for i in issuers],
        "issuerNote": None if issuers else "The body that issues this has not been collected for your country.",
        "priceNote": ("In your country the state issues this itself, so the vendor price ranges in our sources do not apply "
                      "and none is shown.") if n.state_route else None,
        "prerequisites": prerequisites, "parallelWith": parallel_with,
        "verificationStatus": req.status, "lastReviewed": req.last_reviewed,
        "sourceUrl": req.source_url,
    }


def _related(a: str, b: str, edges: list[tuple[str, str, str]]) -> bool:
    """Whether one step is (transitively) before the other."""
    def before(x: str, y: str) -> bool:
        stack, seen = [x], set()
        while stack:
            cur = stack.pop()
            if cur == y:
                return True
            seen.add(cur)
            stack.extend(c for p, c, _ in edges if p == cur and c not in seen)
        return False
    return before(a, b) or before(b, a)


def _branch_note(req: Requirement, n: _Node, statuses: Mapping[str, str], content: Content) -> str | None:
    """The ISO 9001 branch in words: which range is shown and why."""
    extra = req.extras.get("without_prerequisite")
    if n.variant_used:
        held = content.requirements[n.variant_used].name
        return f"You hold {held}, so the range the source gives for a firm that already holds it is used."
    if extra and not n.state_route and statuses.get(extra["requirement"], "not_held") not in DONE:
        return extra["text"]
    return None


def call_timing(assessment: Assessment, roadmap: Mapping[str, Any], deadline: datetime | None,
                now: datetime) -> dict[str, Any]:
    """Can a company take part in a call of this programme before the deadline?

    realistic: 'yes' (every step fits even in the slowest case), 'maybe' (only the fastest case
    fits), 'no' (not even the fastest), 'not_possible' (a rule that no certificate fixes is not
    met), 'depends' (a guarantee or an answer is still needed), 'unknown' (no deadline), 'closed'
    (the deadline has passed).
    """
    days_left = None if deadline is None else (deadline - now).total_seconds() / 86400
    steps = [s for s in roadmap["steps"] if assessment.programme in s["blockingFor"]]
    fixable = {s["code"] for s in steps}
    structural = [r for r in assessment.rules
                  if r.rule in assessment.blocking and r.requirement not in fixable]
    totals = roadmap["totals"]["days"]
    out: dict[str, Any] = {
        "programme": assessment.programme, "verdict": assessment.verdict,
        "deadline": deadline.isoformat() if deadline else None,
        "daysLeft": None if days_left is None else round(days_left, 1),
        "steps": [s["code"] for s in steps],
        "fastestPathDays": {"min": totals["min"], "max": totals["max"]} if steps else {"min": 0, "max": 0},
        "notFixable": [{"rule": r.rule, "title": r.title, "reason": r.reason} for r in structural],
    }
    if days_left is not None and days_left < 0:
        out["realistic"] = "closed"
        out["text"] = "The deadline has passed."
    elif structural:
        out["realistic"] = "not_possible"
        out["text"] = "A rule that no certificate can fix is not met: " + "; ".join(r.title for r in structural) + "."
    elif days_left is None:
        out["realistic"] = "unknown"
        out["text"] = "The call states no deadline, so the time cannot be compared."
    elif assessment.verdict == "eligible":
        out["realistic"] = "yes"
        out["text"] = "No blocking rule is open: you can apply now."
    elif not steps:
        out["realistic"] = "depends"
        out["text"] = "No certificate is missing, but a guarantee or an answer is still needed."
    elif totals["max"] <= days_left:
        out["realistic"] = "yes"
        out["text"] = f"The missing steps take up to {totals['max']} days; the call closes in {round(days_left)} days."
    elif totals["min"] <= days_left:
        out["realistic"] = "maybe"
        out["text"] = (f"The missing steps take {totals['min']} to {totals['max']} days; the call closes in "
                       f"{round(days_left)} days. It works only if everything goes at the fast end.")
    else:
        out["realistic"] = "no"
        out["text"] = (f"The missing steps take at least {totals['min']} days; the call closes in "
                       f"{round(days_left)} days.")
    # A guarantee, a condition or an answer that is still open is not fixed by a certificate: "the steps fit" is not "yes"
    # (V2-B2: a Ukrainian company for the EDF has a PIC to obtain and an association agreement that is not confirmed).
    if out["realistic"] == "yes" and (assessment.conditions or assessment.incomplete):
        out["realistic"] = "depends"
        out["text"] += " A condition or an answer is also still open in the rules, so this is not a plain yes."
    return out

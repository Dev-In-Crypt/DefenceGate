"""The readiness content as plain data: requirements, issuers, programmes and their rules.

One shape, three producers: the seed file (`seed.parse`), the database (`seed.read_content`) and
the tests. The engine and the roadmap take a `Content` and know nothing about where it came from,
so they stay pure functions and are tested without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Expr = dict[str, Any]


@dataclass(frozen=True)
class Money:
    """A cost range as a source states it. `basis`: free | vendor_range | not_stated. Money is
    never converted: `alt` is a second figure the source itself gave in another currency."""
    min: float | None
    max: float | None
    currency: str | None
    basis: str
    text: str | None = None
    alt: dict[str, Any] | None = None


@dataclass(frozen=True)
class Span:
    """A duration range in calendar days, with the words of the source."""
    min: int | None
    max: int | None
    text: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Variant:
    """A different cost or duration when another requirement is already held (an AQAP 2110
    certificate costs less for a firm that already holds ISO 9001)."""
    when_held: str
    cost: Money | None
    days: Span | None
    source_text: str


@dataclass(frozen=True)
class Issuer:
    requirement: str
    country: str
    name: str
    url: str | None
    notes: str | None
    status: str
    state_route: bool = False        # the state itself issues it: commercial price ranges do not apply


@dataclass(frozen=True)
class Requirement:
    code: str
    name: str
    category: str
    kind: str
    summary: str
    description: str | None
    cost: Money | None
    days: Span | None
    variants: tuple[Variant, ...]
    extras: dict[str, Any]
    legal_basis: str | None
    mandatory_for: str | None
    source_url: str
    source_ref: str | None
    source_text: str | None
    text_origin: str
    status: str
    last_reviewed: str
    position: int = 0
    prerequisites: tuple[tuple[str, str], ...] = ()      # (requirement code, relation)
    issuers: tuple[Issuer, ...] = ()


@dataclass(frozen=True)
class Rule:
    programme: str
    code: str
    title: str
    obligation: str                  # mandatory | conditional | recommended
    kind: str
    requirement: str | None          # the requirement that would fix an unmet rule
    applies_when: Expr | None
    condition: Expr | None           # true when the rule is met; None = information only
    conditional_when: Expr | None    # when the condition fails: true = a derogation may apply
    texts: dict[str, str]
    note: str | None
    denominator: str | None
    source_url: str
    source_ref: str
    source_text: str
    text_origin: str
    status: str
    last_reviewed: str
    position: int = 0


@dataclass(frozen=True)
class Programme:
    code: str
    name: str
    summary: str
    kind: str                        # programme | route | general
    legal_basis: str | None
    source_url: str
    call_programme: str | None
    last_reviewed: str
    position: int = 0
    rules: tuple[Rule, ...] = ()


@dataclass(frozen=True)
class Content:
    programmes: dict[str, Programme]
    requirements: dict[str, Requirement]
    reviewed: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def issuers_for(self, code: str, country: str | None) -> list[Issuer]:
        """The issuers of a requirement for a country: its own rows, else the '*' rows (one body
        for every country), else nothing. Nothing means "not collected", never a guess."""
        req = self.requirements.get(code)
        if req is None:
            return []
        own = [i for i in req.issuers if country and i.country == country]
        return own or [i for i in req.issuers if i.country == "*"]

    def rules_of(self, requirement: str) -> list[Rule]:
        """The rules that name a requirement as what would fix them, and, for an eligibility rule that is
        assessed and not obtained (`extras.rules`), the programme rules it stands for."""
        listed = set(self.requirements[requirement].extras.get("rules", [])) if requirement in self.requirements else set()
        return [r for p in self.programmes.values() for r in p.rules if r.requirement == requirement or r.code in listed]

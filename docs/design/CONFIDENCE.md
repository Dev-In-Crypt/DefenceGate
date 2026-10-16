# Classification confidence (WP-23, 16 October 2026)

Why: every card says why a notice is listed, not how sure we are. Measured precision of the default list is not
uniform (round 2: core strictly 57 %, leniently 81 %, clearly not defence 6 %). A reader who relies on "defence"
needs to see the difference. Decided before building: signals stay separate columns; the level is **derived at read
time** from them by one pure function (`backend/dgate/confidence.py`); three levels; no percentage on a card; the
verdict `is_defence`, the scope and `qualifiedBy` do not change. No migration was needed.

## 1. The signal combinations on the list today

Production, 16 October 2026, scope `relevant` (core and supply together), every status, 304,958 stored notices
(read-only SQL over `opportunity`; the list's collapse rules are not applied). Signals: `LB` legal basis 2009/81/EC,
`CPV` military product code, `BUY` buyer on the defence list, `LNK` linked to a defence notice of another source.

| Cell | Combination | Notices | Level |
|---|---|---|---|
| A | LB + CPV + BUY | 16,661 | high |
| B | CPV + BUY (no LB) | 13,987 | high |
| C | LB + BUY (no CPV) | 28,304 | medium |
| D | BUY only | 224,413 | medium |
| En | LB + CPV, no BUY, buyer class defence / other / unclassified | 542 | medium |
| Es | LB + CPV, no BUY, buyer class security or civil | 680 | low |
| F | CPV only (no LB, no BUY), not a security body | 4,653 | low |
| G | CPV only, buyer a police / prison / border / customs / tax body (`security_buyer_cpv`) | 5,278 | low |
| H | LB only, buyer a civil body (`directive_civil_buyer`) | 7,132 | low |
| J | LB only, buyer class defence / security, or linked | 3,042 | low |
| K | LNK only | 266 | low |

The cells partition the list. `LNK` does not change a cell where another signal is present.

## 2. The rule

```
CPV and BUY                                   -> high
BUY (no CPV)                                  -> medium
LB and CPV, buyer class defence/other/none    -> medium
anything else                                 -> low
```

`basis` is the list of signals present, in plain words, followed by what is missing or doubtful ("No military
product code in the notice", "Buyer is not on the defence list", "Buyer is a police, prison, border, customs or tax
body"). The SQL twin (`CONFIDENCE_SQL`) is used by the optional `confidence` filter of `/v1/tenders`.

## 3. Why these levels (measured, `docs/verification/ux/confidence-sample.md`)

A level is a statement about the notices that receive it. Sample of 363 notices, drawn at random and stratified by
source inside each cell, labelled Y (defence goods or services themselves), G (a defence body buying something
generic), B (borderline: police, research, undecidable), N (not defence). Strict = Y; lenient = Y + G.

| Level | Sample | Strict | Lenient | Not defence |
|---|---|---|---|---|
| high | 64 | 96 % (88 to 98) | 99 % (92 to 100) | 0 % (0 to 6) |
| medium | 111 | 11 % (6 to 19) | 93 % (85 to 97) | 0 % (0 to 3) |
| low | 188 | 14 % (9 to 19) | 21 % (16 to 27) | 34 % (28 to 40) |

- **High** needed at least 90 % lenient on at least 60 notices (owner constraint). Cells A and B together meet it with
  margin: 63 of 64 lenient, Wilson lower bound 92 %. Cell C (the directive plus a defence buyer, no military code)
  also scores 97 % lenient but only 28 % strict (22 of 32 are ordinary purchases by a defence body), so it is not
  high: **high means the item and the buyer both say defence**, which is stricter than the owner's minimum.
- **Medium** is "the buyer is a defence body": 93 % lenient, none clearly not defence, but only about one in nine is
  itself defence goods or services. It is 83 % of the list (cell D alone is 74 %). The card says so ("No military
  product code in the notice").
- **Low** is the weak groups: a single signal from a security or civil body, or a code alone. A third of them are not
  defence at all, another third borderline. Round 2 had already found these groups weaker (the two groups of 14
  October are cells G and H).
- Strict precision is not monotone (medium 11 %, low 14 %): low holds military construction by civil building
  authorities that is defence (cell F, 13 of 36 Y) and medium holds generic purchases. Lenient precision and the
  share of clearly-not-defence notices are monotone. The methodology page gives all figures and says which is which.

## 4. What was left out

- A buyer class of `defence` without the buyer being on the list (about 850 notices on the list) is not raised to
  medium when it has a single signal: the sample held five such notices (all generic purchases), too few to claim.
- A stored column for the level: not needed. The `confidence` filter adds a condition to the existing parallel scan
  of the default list (`EXPLAIN` on production: same plan, no new sequential scan); an index to filter by level would
  only matter if the filter became the default.
- Model enrichment, per-user settings, any change of the verdict: out of scope.

## 5. Keeping it true

The measured figures are a sample estimate of 16 October 2026 and are printed with that date on the methodology page.
A change of the classifier or of the buyer list changes the cells; re-run the sampling (queries and rubric in the
sample file) before editing the figures. `tests/unit/test_confidence.py` pins the table; `tests/integration/
test_confidence.py` keeps the SQL twin in step with the function.

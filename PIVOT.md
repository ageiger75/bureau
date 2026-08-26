# Decision Room → CEO Performance Cockpit

Answer to §36 of `CEO_Performance_Cockpit_Build_Brief_V1.md`: what exists, what is reused,
what is set aside, and the smallest refactor that gets from one product to the other.

Written before any code was changed, and kept as the record of why the repository looks
the way it does.

---

## 1. What existed

Decision Room: a working prototype, 202 tests, built around a different question — how a
CEO frames and takes a decision. Roughly 4 600 lines of application code, with a strict
separation between pure business rules (`app/domain/`), persistence, and HTTP.

That separation is the reason this pivot cost days rather than weeks: the rules that
transfer were never entangled with the screens that do not.

## 2. What is reused, unchanged

| Component | Why it survives the pivot |
| --- | --- |
| `app/config.py` | Carries the guardrails the new brief asks for in §32 — `EXECUTE` refused by the code, listening address fixed to the loopback, no outbound client. Already written, already tested. |
| `app/db.py`, `app/util.py`, `app/web.py`, `app/main.py`, `app/cli.py` | Plumbing with no opinion about the product. |
| `app/domain/warnings.py` | Every signal carries a code, a message **and** a fix. The cockpit needs exactly that shape. |
| `app/domain/commitments.py` | Alert levels, overdue rule, summary, and the refusal to let an action exist without an owner or a date. This is most of brief §17–§18, already built. |
| `app/static/ceo-os.css` | Sober, dense, colour reserved for signalling. Brief §28 describes the same thing. |

## 3. What is reused in spirit

- `app/domain/claims.py` separates sourced fact, hypothesis, opinion and missing
  verification. Brief §16 asks for DATA / INTERPRETATION / CONFIDENCE / MISSING DATA — the
  same discipline under different names.
- `app/domain/challenge.py` records an objection, its evidence, the response and what
  remains unanswered. Brief §21B (Commercial Challenger) is that mechanic applied to a
  management explanation rather than to a decision premise.

## 4. What is set aside

`app/domain/cases.py`, `app/domain/reviews.py`, and the options / recommendation /
decision / review screens — about 1 200 lines. Brief §33 explicitly rules out "complex
decision frameworks" and "generic decision matrices".

**Nothing is deleted.** Decision Room keeps working at `/decisions`, with its own tests
green. It stopped being the front door; it did not stop existing. Deleting a tested,
working product to make room for an unproven one is a trade worth refusing until the
cockpit has earned it.

## 5. The minimum refactor

Four moves, no rewrite:

1. A new package `app/perf/` holding the normalised model, the deterministic analytics and
   the data source. It imports from `app/domain/` where rules already exist.
2. `GET /` becomes the Today screen. Decision Room's home moves to `/decisions`.
3. The shared chrome — top bar, scope banner, footer — follows the primary product into
   English. Decision Room's own screens stay French and declare `lang="fr"`.
4. Commitment intelligence extends the existing rules rather than replacing them.

## 6. The seam that matters

```
data source → normalised performance model → analytics engine → interface
```

`app/perf/source.py` is the only module that knows where numbers come from. Nothing above
it imports `mock`. Connecting a warehouse (brief §35, Phase 6) is a change in that one
file.

## 7. Where the phases stand

| Phase | Content | State |
| --- | --- | --- |
| 1 | Today screen on mock data | **Done** |
| 2 | Deterministic analytics | **Done** — built with Phase 1, because a Today screen showing hardcoded numbers that contradict each other cannot answer the question Phase 1 exists to ask |
| 3 | Investigate — drill-down | Not started |
| 4 | Commitments screen and storage | Partly — the intelligence exists and is read on Today; nothing is stored yet |
| 5 | Performance Chief of Staff | Not started, and announced as such on screen |
| 6 | Real data | Not started; the seam is in place |

Phase 2 was pulled forward deliberately. The brief's own success test (§34) is whether the
screen makes a CEO want to act — and a screen whose numbers do not add up would fail that
test for the wrong reason.

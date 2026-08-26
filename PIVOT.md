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

## 7. The KPI layer

Sales decompose into drivers. A managed KPI does not: it is a number somebody owns, with a
target somebody agreed, reported on a cadence somebody set. `app/perf/kpi.py` reads them
under three rules, each taken from the FY27 tracker itself rather than assumed:

| Rule | Why it exists |
| --- | --- |
| **Cadence governs freshness** | A quarterly KPI has no August value. Reporting it missing every month would teach the reader to ignore the flag — and then the real gaps go unread too. |
| **Direction decides what a gap is** | Retail turnover above target is bad news; a brand ranking above target is good news. A positive gap always means good news, whichever way the KPI should move. |
| **A provisional definition suspends the challenge** | Where the definition or target is still moving, the variance is shown and the question is withheld, with the reason. Sending a CEO to challenge someone about a number nobody has agreed costs more than the insight is worth. |

The fiscal calendar runs April to March (`app/perf/fiscal.py`). Q2 FY27 is July–September
2026. Getting that wrong would make the cockpit ask for a quarter that has not closed.

**No real figure from the tracker is in this repository.** The taxonomy is real —
recruitment, active customers, ATV, NPS, CLV, retail turnover — because that is what has
to be monitored. Every value, target and owner in `mock.py` is invented, as the repository
has required from the start.

## 8. Connecting real data, one source at a time

Client and sell-out data exist today; sell-in is coming. The layer is built for that to
arrive in pieces rather than in one cut-over:

- A KPI with no reading reports `No reading yet`. It never guesses, and never shows a
  stale figure as current.
- A KPI absent from the source simply does not appear. Nothing breaks.
- `source.py` returns three things — the sales dataset, the commitments, the KPIs. A real
  source can serve one of them and leave the others mocked while IT works through them.

The practical order follows what is already available: client KPIs first (recruitment,
ARC, ATV — the data exists), then sell-out into the sales drivers, then sell-in. Each step
is a change inside `source.py`; nothing above it moves.

## 9. Reading the warehouse

Snowflake access is built and switched off. Two things must be said out loud before
anything leaves the machine — a source (`CEOOS_DATA_SOURCE=snowflake`) and a connection
name (`CEOOS_SNOWFLAKE_CONNECTION`) — and the default is neither.

**No credential lives in this application.** It names an entry in
`~/.snowflake/connections.toml`, the file the Snowflake CLI and Cortex Code already
maintain, and the connector resolves it. There is no secret to leak from this repository
and no password to rotate.

**Reads only, twice over.** `app/perf/warehouse.py::assert_read_only` refuses anything that
is not a SELECT, WITH, SHOW, DESCRIBE or EXPLAIN, rejects any write keyword anywhere in
the body, and refuses a second statement smuggled behind a semicolon — all before a
connection is opened. That is the second lock. **The first belongs to whoever administers
Snowflake: a role with no write grant.** Code cannot grant itself permissions it lacks,
and should not be trusted to withhold ones it holds.

**The connector is optional.** Pinned to `snowflake-connector-python==4.5.0`, because 4.7
and later require Python 3.10 while the workstation runs 3.9.6. It is never installed by
default, and the whole test suite passes without it.

**The queries are not written.** `app/perf/queries.py` holds six named placeholders and a
precise description of what each must return. An unwritten query raises rather than
returning an empty list — a calm-looking cockpit on a business with problems is the most
expensive lie this product could tell. `manage.py check` lists what is still missing;
`manage.py warehouse` proves the connection works without reading any business data.

One rule to preserve when writing them: **prefer measures the organisation has already
modelled to recomputing from raw tables.** A cockpit whose number differs from the one in
a team's report loses the argument in the room, whatever its arithmetic says.

## 10. Where the phases stand

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

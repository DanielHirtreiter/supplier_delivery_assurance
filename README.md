# Supplier Delivery Assurance

A focused 12-week supplier assurance demonstration: open schedule lines, source evidence, delivery commitments, targeted clarification, buyer review and management monitoring.

Start with [START_HERE.md](START_HERE.md) for Windows/macOS setup in VS Code.

## Run locally

The core worklist requires Python 3.10+ and a current desktop browser. Monte Carlo requires Python 3.11+ and the pinned scientific dependencies: `python -m pip install -r requirements.txt`. No build step, API key or cloud account is required. See [MONTE_CARLO.md](MONTE_CARLO.md) for the model, controls and assumptions.

```sh
python app.py
```

Open **http://127.0.0.1:8000**. The server binds only to loopback. Use `python app.py --port 8001` to change the port. SQLite data and revision snapshots are created in `.runtime/assurance.sqlite3`. Restarting the app restores the workspace.

## Economic impact update

Open **Economic impact**, edit supplier exposures, delays, stock cover, contribution margins and expediting assumptions, then run a reproducible Python Monte Carlo simulation. Compare baseline and expediting, inspect supplier-level losses, portfolio P95/ES95 and numerical-precision diagnostics. Export assumptions and results for replay. Full details: [MONTE_CARLO.md](MONTE_CARLO.md).

## Demonstrate in five minutes

1. Click **Run walkthrough**. The initial portfolio has 8 fictional suppliers, 32 schedule lines and 2 plants.
2. Open **Nordwerk Components**, then its first schedule line. Compare the business requirement (1,200 PC) with the supplier's split delivery: 720 on time and 480 ten days late. Inspect the original message and evidence excerpts.
3. Click **Draft clarification**. Review the selected lines, recipient, response deadline and targeted questions. Save the draft, or check the approval box and click **Approve & simulate send**.
4. Click **Process reply**. Choose the prepared English or German recovery example, click **Extract facts**, check the PO matches and record the result for buyer review.
5. Open **Review & validate**. Check the source, add your rationale, confirm verification and validate. The first line now has full on-time coverage; the other requested line stays open until its own reply is received. The original statement and SAP snapshot remain intact.
6. Inspect **Management overview** or export the worklist to CSV. Use **Rules & data → Reset demonstration** for the next walkthrough.

The snapshot is fixed at **7 September 2026** for a reproducible webinar. Changing it in Rules & data recalculates freshness, overdue requests and the 84-day horizon. This is a scenario clock, not the computer's current date.

## What is implemented

- Supplier worklist with search, plant/buyer/status filters and a clickable 12-week horizon.
- Separate required, SAP-confirmed and supplier-stated quantities/dates.
- Original source messages and excerpts, previous commitments, split deliveries and evidence freshness.
- Independent delivery, information and case-process statuses.
- Conservative extraction of explicit English/German commitments, including multiple PO sections.
- Editable, consolidated supplier requests with buyer approval and simulated sending.
- Partial-response tracking: a reply for one line does not close another line's request.
- Buyer corrections and rationale, next-action ownership, manual case resolution and activity history.
- CSV export, JSON session export/import, configurable freshness and reset.
- A Python standard-library HTTP service, SQLite persistence, append-only workspace revisions and optimistic save conflict detection.

## Scope and honest boundaries

This is a workflow PoV using synthetic SAP-shaped data and prepared supplier messages. **It has no connected LLM, SAP system, mailbox or autonomous agent.** There are no external-send or SAP-write endpoints. The demonstration shows how evidence collection, matching, extraction, deterministic assessment and human review fit together.

The extraction engine accepts explicit patterns such as:

```text
PO 4500012001, item 10, schedule 1.
Delivery: 1200 PC on 2026-09-11.
Dispatch: 2026-09-10.
Cause: Machine failure.
Recovery: Backup production line confirmed.
Next update: 2026-09-08.
```

German equivalents include `Bestellung`, `Position`, `Einteilung`, `Lieferung: 1200 Stück am 11.09.2026`, `Versand`, `Ursache`, `Maßnahme` and `Nächstes Update`. Use ISO dates or full German dates. Relative dates, unsupported free-form wording and absent fields remain unknown. The PoV uses integer PC quantities only; formatted thousands such as `1,200` or `1.200` are supported. It does not convert units or calculate probabilities.

The buyer explicitly confirms every message-to-line assignment. Instructions inside a supplier message are treated as text. Missing references can be manually assigned to a verified schedule line, separately from the unchanged original message. Ambiguous explicit references are held for review; the demonstration does not silently guess. Natural-language dates and unsupported phrasing need a future extraction adapter or reviewed structured input.

Text and simple unencoded EML bodies can be loaded. PDFs, scanned documents, complex spreadsheets and encoded MIME attachments are not processed. Source messages are not cryptographically authenticated. Buyer review changes the assessment sidecar, not the source SAP snapshot.

This is a single-user local demonstration, not a multi-user production service. Identity, role-based authorization, verified recipients, durable document storage, retention controls, release-specific SAP adapters, mailbox integration and evaluation of a real language model remain pilot work. The recorded approver is the selected demo buyer, not an authenticated identity. No benefit percentages are promised. The Economic impact screen now calculates a separate, explicitly synthetic Monte Carlo loss model; it does not connect to real BOMs or customer orders.

## Architecture and lean codebase

| File | Responsibility |
| --- | --- |
| `app.py` | Static delivery, JSON API, SQLite revisions and save conflict protection |
| `dist/index.html` | Native application shell |
| `dist/styles.css` | Responsive interface and print styles |
| `dist/app.js` | Screens, buyer interactions and persistence calls |
| `dist/engine.mjs` | Matching, extraction, assessment, request drafting and CSV export |
| `seed.py` / `dist/seed.json` | Reproducible fictional data and supplier evidence |

Business rules live once in the native JavaScript module, shared by the local Python app and the hosted demonstration. Python owns local persistence. There is no frontend framework or npm dependency. Economic impact uses one Python/NumPy/SciPy engine, executed by the local service or by a browser Pyodide worker. The hosted simulation downloads its Python runtime from a pinned CDN; the existing delivery workflow has no external asset dependency.

The hosted browser walkthrough is a **temporary session**: it resets on reload. Export/import carries a session between runs. The same interface served by `app.py` uses real SQLite persistence. It never silently falls back to temporary storage when the local Python service fails.

## Rule details

- The horizon includes today through day 83. Closed/deleted, finally-delivered, zero-open-quantity and overdue inbound lines are excluded from selection. The latter are outside this defined pilot and would need a separate overdue worklist in production.
- On-time coverage sums only explicit supplier delivery legs with arrival date on or before the requirement date. A known incomplete quantity or late leg creates a confirmed shortfall; absent evidence creates unknown status.
- Evidence freshness uses 3 business days for weeks 1–4, 7 calendar days for weeks 5–8 and 14 calendar days for weeks 9–12. Business days exclude weekends, with no public holiday calendar. Defaults are configurable.
- SAP differences and explicit conflicting supplier statements stay visible. Buyer validation can acknowledge the difference without changing SAP. An unresolved source conflict requires an explicit resolution and rationale.
- A stale full commitment, uncertainty, an unverified passed dispatch date, a manual flag or an overdue request for that specific line creates potential risk.
- Evidence coverage counts fresh evidence even when it reports a shortfall. It is not an OTIF or service KPI. Quantities across different materials are not added into a portfolio metric.
- Case closure is a buyer decision with rationale. It marks monitoring resolved while preserving underlying quantities and evidence; it is not an actual goods receipt.

## Verification

```sh
python -m unittest -v test_server.py test_monte_carlo.py
node test_engine.mjs
```

Node 22+ is used only for the optional rule checks; it is not needed to run the app. Tests cover split-delivery arithmetic, missing and stale evidence, German source fidelity, invalid dates, supplier isolation, ambiguous matching, untrusted text, horizon boundaries, business-day freshness, per-line overdue requests, consolidated drafts, recovery, partial replies, immutable SAP fields, export escaping, actual HTTP persistence, revision conflicts and blocked cross-origin saves.

No browser or visual automation was run. HTML asset paths, JavaScript syntax, Python modules, business rules and HTTP behavior were checked.

Regenerate the seed using `python seed.py`. It does not replace an existing SQLite workspace; use Reset demonstration to intentionally restore the prepared cases.

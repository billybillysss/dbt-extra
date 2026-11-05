# Public launch checklist

The goal is useful adoption by dbt practitioners. GitHub Trending placement is
not controllable or guaranteed; no number of README badges or stars proves
correctness. Complete release and onboarding checks before promoting the project.

## Positioning

Lead with one concrete question: **“Where does this dbt column come from?”**
Show the upstream filter and grouping, then the Excel-to-YAML review loop.
Keep optimization, enrichment and AI context as follow-on workflows rather than
five competing opening pitches. dbt-extra complements dbt; it is not a replacement
execution engine, semantic layer, or warehouse performance optimizer.

Suggested repository description:

> Trace dbt column logic, review SQL and metadata in Excel, and preview source edits. Offline; no warehouse credentials or dbt compilation.

Suggested topics, subject to maintainer review:
`dbt`, `sql`, `data-engineering`, `data-lineage`, `sqlglot`, `excel`, `python`, `cli`.
Add only topics that describe implemented behavior. The new dbt-extra repository
remains private during verification; do not change visibility without approval.

## Before inviting users

| Priority | Gate | Verification |
| --- | --- | --- |
| P0 | Public access | Open the repository, raw README assets, Actions badge and issue forms while signed out. An authenticated local checkout does not establish public visibility. |
| P0 | Matching distribution | Verify the private `0.1.0` candidate; publish a new unused version only after separate approval. Follow the [release checklist](releasing.md). |
| P0 | Interfaces | Verify documented commands, native dbt inputs and version-2 settings. Test install instructions against actual artifacts. |
| P0 | Approved artwork | Verify the supplied Modular joint SVG paths, light/dark palette and README rendering. |
| P0 | Reproducible first result | Run the README from a fresh checkout and the published install in a clean environment. Confirm SQL output and preview-only behavior without warehouse credentials. |
| P1 | Trust signals | Confirm linked CI runs passed, package metadata matches the release, and compatibility limitations remain visible. Do not invent benchmarks, adoption figures or supported adapters. |
| P1 | A visible demonstration | Capture the real inspection command and one workbook description edit followed by its YAML diff. Use bundled data, readable terminal text, captions and a text alternative. |
| P1 | Feedback path | Verify issue/PR templates render on GitHub; establish and verify a private security-reporting route. Do not assume private vulnerability reporting is enabled. |

The repository currently supplies source-checkout onboarding, an inspection
example, a description-edit walkthrough, contributor templates, and conservative
safety documentation. A released artifact, hosted demo recording, public settings,
and external adoption require separate verification or maintainer action.

## Launch sequence

1. Ask a small group of dbt users to inspect one real model and attempt one
   metadata-only preview. Collect dialect, coverage reason, time to first useful
   result, and confusing instructions; request redacted reproductions only.
2. Fix onboarding blockers, publish the approved release, and link its known
   limitations and release notes. Update installation instructions against
   the matching package.
3. Share one factual walkthrough in relevant dbt/data-engineering communities,
   respecting each community's promotion rules. Explain the problem and output,
   disclose that you maintain the tool, and invite feedback rather than mass-posting.
4. Turn verified reports into focused issues with reproduction steps. Mark
   genuinely scoped contributor tasks as approachable only after maintainers
   have defined an acceptance test; do not advertise nonexistent issues.
5. Publish follow-ups with actual user-approved examples and tested improvements.
   Keep warehouse speed/cost claims out unless independently measured.

Do not buy stars, use engagement bots, solicit coordinated starring, or send
unsolicited bulk messages. A useful demo and responsive maintenance are the goal,
not manipulating a ranking.

## Measure whether the launch helped

Use available GitHub traffic/referral data and PyPI downloads as directional
signals, not unique-user or successful-install counts. Track first-run failures,
reproduced reports, returning contributors and feedback from users who completed
an inspection or review. Stars are a secondary discovery signal, not the primary
acceptance criterion. No telemetry needs to be added to dbt-extra to run this checklist.

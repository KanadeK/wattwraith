# v0.1.0 release checklist

This file records the release contract for the public v0.1.0 build. Local gates are
reproducible from a clean checkout; GitHub workflow runs and the Release asset checksum
file are the authoritative remote evidence.

| Gate | v0.1.0 evidence |
| --- | --- |
| Name and public-repository sample scan | `docs/COMPETITOR_SCAN.md`, dated 2026-07-23 |
| Authenticated GitHub identity | `KanadeK`, ID `121669563` |
| Four detectors with evidence/confidence | Domain tests and generated demo report |
| Required three standby findings in fixture | CLI/Streamlit E2E assertions |
| Tariff repricing formula | Unit and E2E assertions |
| CSV and JSON | Committed equivalent fixtures and integration tests |
| Privacy and essential-device boundary | Unit, integration, and UI assertions |
| Coverage | 58 tests passed at 90.76%; CI enforces at least 80% overall |
| Build | Wheel and sdist generated successfully by `python -m build` |
| Release assets | Wheel, source archive, sample ZIP, static HTML, SHA256SUMS |
| Clean install | Built wheel installed outside the checkout and analyzed the release sample |
| Author and committer | Every local and remote commit maps to `KanadeK` |
| CI, Security, Pages | Required to be green on `main` before tagging |
| Tag and Release | Annotated `v0.1.0`; workflow-built, non-draft GitHub Release |

Final gate:

```bash
python scripts/release_check.py
```

The script fails on a dirty worktree, version mismatch, missing changelog section,
missing or mismatched assets, test/build failure, high-confidence secret, shell marker,
unknown author/committer, co-author trailer, or a demo missing evidence/confidence and
the required standby findings.

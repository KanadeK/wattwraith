## Summary

<!-- Explain the user-facing problem and the smallest complete change that solves it. -->

## Changes

<!-- List the important implementation, test, and documentation changes. -->

## Verification

<!-- Paste the exact commands executed and their results. -->

```text
python scripts/verify.py
```

## Evidence

<!-- Add real CLI output or current UI screenshots when behavior is visible to users. -->

## Privacy and security

<!-- Explain any impact on local data, exports, dependencies, or trust boundaries. -->

## Checklist

- [ ] The change uses real domain logic and introduces no empty or hard-coded success path.
- [ ] New and changed behavior has unit, integration, or end-to-end coverage as appropriate.
- [ ] `python scripts/verify.py` passes without skipped quality gates.
- [ ] Documentation and `CHANGELOG.md` are updated, or the reason they are not needed is stated.
- [ ] Examples, fixtures, logs, and screenshots contain only synthetic or redacted data.
- [ ] No credentials, personal data, generated caches, or private smart-home exports are included.
- [ ] All new inferences expose confidence, rule rationale, and evidence.
- [ ] Commit author and committer identities are intentional.

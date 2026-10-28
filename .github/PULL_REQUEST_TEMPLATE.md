## Summary

Describe the change and the problem it solves.

## Checklist

- [ ] `python -m unittest discover -s tests -v` passes
- [ ] `python -m compileall -q lib` passes
- [ ] New behaviour is documented (README or `docs/`)
- [ ] Security-relevant changes include a malicious-archive test
- [ ] No new mandatory runtime dependency was added without discussion

## Security impact

Does this change parsing, path handling, limits, symlinks, or external tools?
If yes, describe the threat model and tests.

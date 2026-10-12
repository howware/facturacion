# AGENTS.md

Rules for AI agents (and people) **developing** this howware. To **use** it, the protocol is
[skill/facturacion/SKILL.md](skill/facturacion/SKILL.md).

## Never copy the owner's real data here

- Real documents, exports and the memory (`.memory/`) live in the owner's folder, never in this repository.
- Never open a real invoice (`.xml`), receipt (`.pdf`) or the mxsat private store (`mxsat-private/`), not even to
  "see the format": go through the `mxsat` adapter, whose output is pseudonymized. This tool must never parse
  them itself (a test checks it).
- Tests and fixtures use synthetic data only. If a test needs a valid-looking identifier (card, account), build
  it in code; the guard rejects valid ones written in files.

## Where each change goes

| Change | Where |
|---|---|
| A rule of the job (how the work is done for everyone) | `SKILL.md` |
| A rule the owner teaches (categories, limits, names) | The memory, as data, through the tool — never code |
| An operation that must be exact (matching, money, dates, states) | The tool, with tests |
| Reading or writing SAT documents | The [mxsat](https://github.com/howware/mx-sat-documents) adapter, not here |
| A tax decision (rate, exemption, payment form) | Nowhere in code: it comes from the owner's templates |

## Conventions (howware spec §6, §8)

- Tools: JSON on stdout, errors as JSON with documented exit codes, no prompts, no network, standard library.
- Money in integer cents with a declared unit; dates at noon local time; stable keys for idempotent writes.
- Bump `version` in `howware.json` and the tool's `__version__` together; changing `seed.json` bumps
  `seed_version`.

## Commands

```bash
uv tool install git+https://github.com/howware/mx-sat-documents   # the tests use the real adapter
python -m unittest discover -s tests -v
git ls-files -z | xargs -0 python tools/check_private_data.py
python tools/install_skill.py
```

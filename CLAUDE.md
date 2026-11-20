# Compose keyboards: notes for Claude Code

- Unibody split keyboards generated from Python: `compose/` is the platform, `layouts/<name>/` the layouts. Commands: `python3 -m compose --help`; setup, commands and how to check a change: `docs/building.md`.
- Git: never add trailers or AI attribution of any kind (Co-Authored-By, "Generated with" footers, session links) to commits, PRs, issues or anything on the repo. Work on a branch; the maintainer merges PRs.
- The repo is public: no personal notes, handover files or business plans in it.
- Rev 1 is archived and no longer in the repo: its files are in the release `compose58-rev1`, its source at the tag `compose58-rev1-final`. A change that is not a design change (a reorganisation, a new check) must leave the outputs identical: CI compares them with the base and reports it. See "Checking a change" in `docs/building.md`.
- Every design change gets checked by the existing suites (case checks, DRC, copper simulations) rather than by eye; add a check when a new kind of part or constraint appears.
- Generators target the KiCad 7 Python API.
- Docs voice: plain, concrete, rev 1 / rev 2 naming (never v1 / v2).

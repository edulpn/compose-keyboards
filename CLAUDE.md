# Compose keyboards: notes for Claude Code

- Unibody split keyboards generated from Python: `compose/` is the platform, `layouts/<name>/` the layouts. Commands: `python3 -m compose --help`; setup, commands and how to check a change: `docs/building.md`. The rev follows from the command (`python3 -m compose --help` lists each with its rev); nothing sets it by hand.
- Git: never add trailers or AI attribution of any kind (Co-Authored-By, "Generated with" footers, session links) to commits, PRs, issues or anything on the repo. Work on a branch; the maintainer merges PRs.
- The repo is public: no personal notes, handover files or business plans in it.
- Rev 1 is released and built: changes to shared code must leave its outputs byte-identical (build STLs, BOM, keyboard.json) and its checks passing. See "Checking a change" in `docs/building.md`.
- Every design change gets checked by the existing suites (case checks, DRC, copper simulations) rather than by eye; add a check when a new kind of part or constraint appears.
- Generators target the KiCad 7 Python API.
- Docs voice: plain, concrete, rev 1 / rev 2 naming (never v1 / v2).

# Contributing

Thanks for wanting to improve Compose. Issues, build reports and photos, new layouts, and fixes are all welcome.

## Before you open a pull request

- Run the checks for whatever you touched (`python3 -m compose checks` / `gasket-checks`, the simulations for boards) and say in the PR what you ran and what passed.
- Don't commit generated outputs (`out*/`); releases carry those.
- Keep layouts self-contained: a new layout is a folder in `layouts/` with its key list and hardware positions.

## Licensing of contributions

The keyboard designs here are CC BY-NC-SA 4.0, and edulpn may offer kits or license the designs commercially. So that contributions can be part of that, opening a pull request means you agree that:

1. your contribution is your own work (or you have the right to submit it);
2. it is licensed to everyone under the same terms as the files it changes (CC BY-NC-SA 4.0 for the designs, MIT for the generic helpers); and
3. you also grant edulpn a perpetual, worldwide, non-exclusive, royalty-free license to use, modify, sublicense and commercially exploit your contribution as part of Compose, including under other licenses.

You keep the copyright to your contribution. If you can't agree to point 3, say so in the PR and we'll work it out.

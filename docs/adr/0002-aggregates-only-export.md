# 0002: The public export is aggregates only, with a small-cell rule

- Status: accepted
- Date: 2026-11-12

## Context

The DOL publishes WHD cases row by row, employer names included. This project republishes a derived view of that data in a public repo and on Tableau Public. A cell in a sector × state × fiscal-year table can hold a single case. When it does, the "aggregate" is that one employer's back wages and penalties.

## Decision

- The only public table is `agg_industry_state_year`, at sector × state × federal fiscal year. It holds no case ID, name, address or other row-level field.
- **Small-cell rule:** a cell with fewer than 3 cases keeps its case count. `is_suppressed` is set to true, and every measure is NULL.
- Two tests enforce the rule on the published values:
  - `tests/assert_small_cells_withhold_measures.sql` checks the suppressed measures themselves.
  - `tests/assert_aggregate_grain_and_totals.sql` checks that the cells add up to every dated case, so no case is dropped silently.
- Only the cells are published, with no totals, so a suppressed cell cannot be worked out by subtracting the others from a total.

## Consequences

- Rare sector, state and year combinations show a count but no dollars. On the first partial load, about 43% of cells were suppressed. The share falls as more years load and cells fill up.
- A future export that adds totals, or a finer grain, has to be checked against this rule first.

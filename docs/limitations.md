# Limitations

Stated plainly, because a portfolio project that hides its limits is not credible.

## Data
1. **The default `demo` source is synthetic.** It follows the real Ingolstadt/VGI schemas
   and is statistically realistic, but the numbers describe a simulation, not the city.
   No figure from `demo` mode should be quoted as a fact about Ingolstadt.
2. **`live` mode is partial.** The City of Ingolstadt does not publish an open hourly
   loop-detector feed. Live mode covers weather (DWD), public transport (VGI GTFS) and
   charging infrastructure (OpenStreetMap). Traffic counts require a local export via
   `INGOMOB_TRAFFIC_CSV`.
3. **OpenStreetMap charging data is crowd-sourced** and may be incomplete or stale
   compared with the Bundesnetzagentur register.
4. **The live endpoints were not reachable from the environment this project was built in**
   (no outbound network). The live code path is covered by tests against a local mock
   server that replays the real file formats — the parsers are verified, the production
   endpoints are not. Run `ingomob --source live generate` on a networked machine, or the
   `live-smoke` CI workflow, to confirm.

## Modelling
5. Metrics on synthetic data measure process recovery, not forecast skill — see
   [`model_card.md`](model_card.md).
6. One-hour horizon only; no uncertainty intervals; no event or roadworks feed.
7. The **siting score is an ordinal heuristic**, not an optimisation. It ignores grid
   capacity, land availability, parking turnover and cost. Use it to shortlist, not to decide.
8. Transit analysis uses **scheduled** GTFS data. Without GTFS-Realtime, punctuality and
   actual headway cannot be measured.

## Engineering
9. Single-machine, batch-only. No orchestration, no incremental loads, no CDC.
10. The Java and Python data-quality engines duplicate the rule logic. A test asserts the
    rule names match, but semantic drift is possible in principle.
11. No authentication, multi-tenancy or PII handling — none is needed for open data,
    but this is not a production service.

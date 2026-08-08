# MacroFX backend

This directory is the backend foundation for the MacroFX fundamental terminal.

Planned free/public adapters:
- FRED: US macroeconomic time series
- CFTC: Commitments of Traders
- ECB: euro-area/reference data
- IMF / World Bank: international macro history
- Central-bank public sources where practical
- Public market-price feeds with browser/server-accessible terms

The backend should normalize all observations into a common schema before the
scoring engine consumes them. Missing observations must remain missing; never
substitute invented values.

Recommended normalized observation fields:
`source`, `series`, `country`, `currency`, `timestamp`, `value`, `unit`,
`frequency`, `release_timestamp`, `previous_value`, `revision`, `url`.

Scoring stages:
1. ingest
2. validate
3. normalize
4. persist historical observations
5. calculate currency-level driver scores
6. calculate base-minus-quote pair differential
7. expose REST endpoints to the frontend

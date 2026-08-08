# MacroFX free data architecture

## Sources currently wired

- FRED public graph CSV: detailed US macro series; no FRED API key required.
- World Bank public API: annual GDP growth, CPI inflation and unemployment for USD, EUR, GBP, JPY, CHF, CAD, AUD and NZD country/region aggregates.
- ECB public data API adapter: EUR/USD reference-rate support is available for the market-data layer. It is explicitly not treated as the ECB policy rate.

## Normalization

All stored observations use the common schema:
`source`, `series`, `country`, `currency`, `timestamp`, `value`, `unit`, `frequency`, `release_timestamp`, `previous_value`, `revision`, `url`.

World Bank series are namespaced by currency, e.g. `WB_GDP_GROWTH_EUR`, so one country's history cannot overwrite another country's observations.

## Scoring

The current live scoring layer uses available observations only and reports coverage rather than inventing missing data.

USD:
- Growth: FRED GDP momentum
- Inflation: FRED CPI momentum, inverse direction
- Rates: FRED federal funds rate momentum
- Employment: FRED unemployment + claims + NFP composite

Non-USD supported currencies:
- Growth: World Bank GDP-growth history
- Inflation: World Bank CPI-inflation history, inverse direction
- Employment: World Bank unemployment history, inverse direction

Technicals, retail sentiment, COT, seasonality and central-bank event scoring remain separate adapters and are not fabricated when unavailable.

## Important data-quality note

World Bank international observations are annual. They are useful for historical macro context but are not a substitute for a high-frequency economic calendar or national statistical release feed. The terminal should display frequency/source alongside these observations and keep coverage transparent.

# Data and methods

These definitions reproduce the reviewed Stage 1 report. The frozen snapshot,
not a fresh download, defines the analysis version `dow2015_29`.

## Universe and identity

The starting roster is the 31 October 2015 DJIA cohort, documented in the DIA
annual report's Schedule of Investments.<sup>[1]</sup> Twenty-nine series are
used. Old E. I. du Pont is excluded because the tested sources did not supply
identity-consistent 2015–2017 prices. The current DD series has a different
pre-merger lineage and is not substituted. Original UTX continues as RTX.
The original members remain after index removal; their replacements are not
added. Ordered tickers and inclusion decisions are in `config/universe.json`.

GE, XOM, PFE, UTX/RTX, INTC and VZ subsequently left the DJIA. The dates and
official announcements are preserved in `data/evidence/roster_and_removals.json`.
The 23 retained and six removed groups are defined relative to the stated
cutoff; this classification does not mean the six stocks were exchange delisted.

## Price and return source priority

1. Preserve `data/raw/instructor/prices_us_monthly.csv` unchanged. It contains
   the supplied 21 stocks and nine ETFs; the analysis uses its 15 overlapping
   cohort stocks. Ordinary monthly returns are computed from adjacent supplied
   prices and take priority for October 2016–August 2026, 119 return months.
2. Yahoo daily chart responses supply other stocks and date extensions.<sup>[2]</sup>
   Convert each timestamp to the exchange-local date and retain the last returned
   trading observation in each month. Missing terminal quotes cause an error;
   they are not filled or replaced by an earlier quote. Compute adjacent-month
   simple returns from these observations.
   This gives 131 monthly price observations and 130 returns.
3. Override the seven affected spin-off months with the explicitly reconstructed
   Yahoo-based shareholder return below, including where instructor ordinary
   returns would otherwise have priority. This is a documented exception, not a
   second distribution added on top of adjusted returns.

`vendor_adjusted_prices_us_monthly.csv` contains Yahoo's native monthly adjusted
close. `yahoo_native_returns_monthly.csv` contains its corresponding returns
before instructor priority and event replacement. The final
`returns_us_monthly.csv` is the selected return panel used in every portfolio.

`prices_us_monthly.csv` is a **derived wealth index with October 2015 = 100**,
constructed by compounding the final selected returns. It is not a USD-per-share
price table. `month_end_observation_dates.csv` records Yahoo's actual final
trading observations; it does not independently certify the date convention of
the instructor source. All final return columns share 130 months and contain
no missing values.

## Mandatory spin-off distributions

We use one continuing return series per original member. At an event close,
shareholder wealth includes the continuing share and all automatically received
child shares. The child shares are sold at that close and the proceeds reinvested
in the continuing share. Normal days retain the provider-adjusted return.

| Continuing series | Event date | Received per pre-event share |
|---|---|---|
| UTX → RTX | 2020-04-03 | 1 CARR + 0.5 OTIS |
| PFE | 2020-11-17 | 0.124079 VTRS |
| MRK | 2021-06-03 | 0.1 OGN |
| IBM | 2021-11-04 | 0.2 KD |
| GE | 2023-01-04 | 1/3 GEHC |
| MMM | 2024-04-01 | 0.25 SOLV |
| GE | 2024-04-02 | 0.25 GEV |

The cached daily quote closes have split-adjusted units. Restore each parent
and child quote to its event-date share units using that security's split
inventory before applying the distribution ratio. Divide reconstructed closing
wealth by the preceding parent close to obtain event-day gross return. Divide
this gross return by Yahoo's native event-day adjusted-price gross return to
obtain a replacement multiplier. Multiply the **native Yahoo monthly gross
return** by this multiplier, then subtract one. No event coincides with an
ordinary cash-dividend ex date in the retained snapshot.

The independent event code checks these calculations from cached quotes and
official terms. The frozen calculations are in
`data/evidence/corporate_action_economic_corrections.json`; generated checks are
in `validation/`. This explicit reinvestment convention replaces the provider
event return; it does not double-count child-share wealth. It also does not
maintain a permanently expanded portfolio of child companies.

## Capitalization and factors

Yahoo `monthlyMarketCap` records are selected at **2026-08-31**, period type
`1M`, currency `USD`, one record per ordered stock.<sup>[2]</sup> Value weights
are each company's reported capitalization divided by the 29-company total.
No capitalization is fabricated from today's shares outstanding or from
adjusted prices. The weights are held fixed throughout the return window.

The factor source is the official US Fama–French three-factor CSV, created
from the 202608 database.<sup>[3]</sup> It contains `Mkt-RF`, `SMB`, `HML` and
`RF`. Convert published percentage numbers to decimal monthly returns by
dividing by 100 **once**, and retain exactly November 2015–August 2026. RF is
the library's one-month Treasury-bill series; the header records its source
change beginning June 2024. Daily and weekly factor files are not part of this
snapshot.

## Portfolio estimation

- Estimate raw-return arithmetic monthly means and the sample covariance with
  `ddof=1` (denominator 129 for 130 observations).
- Subtract the window's mean RF from each stock's mean. Solve the covariance
  linear system for this excess-mean vector, then normalize the direction so
  portfolio weights sum to one. Short weights are allowed. Covariances are
  positive definite; no shrinkage, pseudoinverse or weight clipping is used.
- Long-only tangency maximizes the same model Sharpe with nonnegative weights
  summing to one. Production uses an equivalent convex quadratic formulation
  with SLSQP, analytic gradients and KKT checks. Independent validation uses a
  separate nonnegative least-squares route.
- Every raw monthly portfolio return is the ordered stock-return vector times
  its fixed weight vector. Portfolios rebalance to these weights monthly.
- Annualized arithmetic mean is monthly mean multiplied by 12. Annualized
  volatility is monthly sample standard deviation multiplied by the square
  root of 12. **Model Sharpe** is annualized mean excess return divided by
  annualized **raw-return** volatility. The separately named realized-excess
  Sharpe instead uses excess-return volatility.
- Gross exposure is the sum of absolute weights. Net exposure is the sum of
  weights, equal to one. Means are arithmetic, not compounded growth rates.

The first window is November 2015–March 2021; the second is April 2021–August
2026. Each contains 65 observations and re-estimates mean, covariance and mean
RF. Each time-comparison table uses the portfolio's **own fitting window**.
The separately reported first-half-weights-on-second-half result uses second
half returns without refitting those weights.

Universe sensitivity holds the full 130-month window fixed and independently
fits 29, 23 and six-stock portfolios. Outside-subset weights are stored as
missing in the comparison CSV because no weight was estimated for that asset.
The plotting copy uses zero to show that it is not held. Status subsets are
ex-post comparisons, and different numbers of investment opportunities affect
the fitted optimum. Fixed sample-end value weights are a descriptive comparator,
not a historical capitalization index. Costs are excluded from these calculations.

## References

[1] SEC / SPDR DIA, [Annual report for October 31, 2015](https://www.sec.gov/Archives/edgar/data/1041130/000119312515412510/d84289dn30d.htm),
Schedule of Investments, printed p.2.

[2] Yahoo Finance public chart and fundamentals-timeseries responses. Exact
request URLs, parameters and retrieval times accompany each cached response in
`data/raw/`; `monthlyMarketCap` is the returned provider field.

[3] Kenneth R. French, [Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html),
US Fama–French Research Data Factors, 202608 snapshot. Source CSV retained in
`data/raw/french/`.

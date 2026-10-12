# Monte Carlo economic impact

The **Economic impact** screen adds a real Python simulation to the delivery-assurance workflow. It is a synthetic economic-impact PoV, not a calibrated supplier prediction or a connected production-planning model.

## Run

For Monte Carlo, use Python 3.11+ with the pinned NumPy/SciPy versions:

```sh
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`, select **Economic impact**, review the supplier assumptions and click **Run simulation**. The existing worklist remains usable without installing simulation dependencies. `/api/simulate` returns an explicit setup error if the scientific packages are missing; it never supplies fabricated fallback results.

For an independent, reproducible run:

```sh
python dist/monte_carlo.py dist/economic-example.json --output result.json
python -m unittest -v test_monte_carlo.py test_server.py
node test_engine.mjs
```

The native HTML/CSS interface calls the Python service locally. The static hosted build uses the **same Python files** in a Pyodide Web Worker with NumPy and SciPy. It fetches the pinned Pyodide 0.28.3 runtime from jsDelivr on the first run. Browser runtime loading requires access to that CDN; no user simulation data is sent to it. Failed loading produces a visible error. Local execution does not use the CDN. Runtime versions may differ, so seed alone is not a promise of identical native/browser draws.

## Input basis and scope

The model aggregates each included supplier into one disruption episode. The initial selection contains suppliers with confirmed shortfalls in the current 84-day worklist. Known late quantities initialize **exposed finished units with an explicit synthetic 1:1 conversion**. The largest stated lateness is a representative lower bound for that supplier; mode is three days longer and the upper bound twelve days longer, capped at 84. Where the supplier has not committed a recovery date, the initial 2/5/14-day bounds are assumptions, not extracted dates.

These are editable approximations. Different lines may recover at different times; the model does not simulate their schedules individually. The real data needed to replace the assumptions are BOM conversion, stock by material, production/customer-order allocation, consumption rates, contractual terms, unit contribution margins and credible recovery distributions.

Portfolio addition assumes **disjoint downstream exposures**. If several suppliers affect the same customer order, do not sum their separate loss estimates; a joint BOM/order-allocation model is required. The interface states this limitation prominently.

| Driver | Unit / horizon | Model | Basis / dependence | Financial treatment |
| --- | --- | --- | --- | --- |
| Occurrence | Probability per 84-day exposure | Bernoulli | 1 for confirmed shortfalls; other suppliers excluded by default, hypothetical 0.3 if included | Occurrence gates severity; not probability × deterministic loss |
| Supplier delay | Days late, conditional on occurrence | Triangular min/mode/max | Elicited bounds; independent supplier uniforms plus a shared stress regime | Reduced by stock cover; capped at 84 days |
| Shared stress | Probability per scenario / extra days | Bernoulli plus fixed severity increment | Same shock draw for all suppliers; affects delay, not occurrence | Creates joint severity dependence without a second loss entry |
| Exposed volume | Finished units | Fixed cap | Synthetic conversion from source shortfall; must be disjoint across suppliers | Caps affected demand |
| Consumption | Finished units/day | Fixed rate | Synthetic; no demand forecast model | Converts uncovered days into affected units |
| Stock cover | Days | Fixed | Existing inventory, no new investment assumed | Absorbs delay before financial impact |
| Cancellation fraction | Fraction of affected volume | Triangular min/mode/max | Independent per supplier and of severity; editable synthetic assumption | Only canceled volume loses contribution margin |
| Price / margin | EUR/finished unit | Fixed | Synthetic; margin includes avoided variable cost | Revenue and margin are never both added to loss |
| Penalty | EUR/affected unit/uncovered day | Fixed rate × simulated exposure | Synthetic, uncapped by contract | Additional loss; validate real contractual caps separately |
| Extra disruption cost | EUR/uncovered day | Fixed rate × simulated days | Only incremental cost beyond normal fixed costs | Additional loss |
| Expediting | Saved days, lead time, unit capacity, success probability | Conditional Bernoulli success | Triggered only if baseline uncovered units > 0 | Fee is paid on attempt, premium only on recovered units |

The threshold is a user-selected **economic-loss threshold**, not a liquidity limit, legal capital requirement or risk-appetite recommendation. The €100,000 default is illustrative. No booked risk allowance is present in the deterministic baseline.

## Deterministic equations

For supplier `i`, let `B` be occurrence, `S` common stress, `D` conditional delay, `C` cancellation fraction, `Q` exposed volume, `r` daily demand and `b` stock-cover days.

```text
delay = B × min(84, D + S × shared_extra_days)
uncovered_days = max(0, delay − b)
affected_units = min(Q, r × uncovered_days)

permanent_lost_contribution = affected_units × C × unit_margin
penalty = affected_units × uncovered_days × penalty_per_unit_day
extra_cost = uncovered_days × extra_cost_per_day, only if affected_units > 0
economic_loss = permanent_lost_contribution + penalty + extra_cost

recoverable_delayed_revenue = affected_units × (1 − C) × selling_price
```

Recoverable delayed revenue is informational and excluded from loss. The model does not assign all deferred revenue to lost sales or forecast which accounting quarter receives it. It models incremental economic loss attributable to a bounded disruption, not complete quarterly P/L, cash flow or liquidity. Recovery and costs beyond the 84-day cap are excluded.

For successful expediting, effective delay cannot fall below intervention lead time, cannot exceed the original delay, and cannot recover more than the specified quantity capacity. The same cancellation propensity and primitive scenario rows are used for baseline and expediting. Intervention expense is added to residual economic loss. A failed or expensive action can have negative net savings.

## Outputs and uncertainty

- Mean, median, P5/P95, VaR95 and exact empirical ES95, with larger loss worse.
- Supplier-level results plus total-portfolio loss distributions and exceedance curves.
- Expected lost contribution, penalties, extra cost, recoverable delayed revenue and expediting spend.
- Paired net savings and their mean confidence interval; probability expediting is cheaper for the portfolio.
- Portfolio-tail supplier contributions using fractional tail weights; these sum to portfolio ES95. Standalone supplier P95 values do not add.
- Student-t Monte Carlo confidence intervals for means, exact binomial intervals for threshold probabilities, and a 100-resample diagnostic percentile bootstrap for P95/ES95.
- Independent 1,000-scenario pilot, separate production stream and separate bootstrap stream. The pilot sample recommendation uses the requested mean tolerance and a conservative ±1 percentage-point breach-probability target. Meeting the mean target does not establish tail convergence.
- Stress with the common event forced on, plus sampled common-shock frequency and achieved supplier-loss correlations. Separate one-at-a-time parameter stresses increase delay upper bounds by 50%, fix cancellation fractions at their elicited upper bounds, and reduce contribution margins by 25%. These use common primitive draws and are sensitivity cases, not parameter confidence intervals.
- Spearman associations of delay and cancellation with loss in the exported supplier results; these are screening associations, not causal importance or additive attribution.

The distributions describe variability **conditional on assumed parameters**. Parameter uncertainty has not been calibrated. Change assumptions and rerun; more samples do not make synthetic inputs more reliable. Bootstrap intervals can be misleading at atoms or sparse tails. Predictive P5/P95 ranges are not confidence intervals for the mean.

## Reproducibility and persistence

Each exported result contains its full configuration, model version, code/config SHA-256 hashes, Python/NumPy/SciPy versions, seed, bit generator, number of production rows and sampling design. Configurations can be saved with the workspace and are included in JSON session exports. Results are exported separately. Changing economic inputs invalidates displayed results; changing source evidence requires refreshing worklist exposure before another run.

`dist/mc_core.py` is reused unmodified from the Monte Carlo Simulation in Python skill. `dist/monte_carlo.py` separates validation, sampling, deterministic evaluation and reporting. There is no JavaScript reimplementation of the statistical model.

## Validation and sources

Checks cover deterministic accounting, no event, no exposure, full stock cover, expediting capacity and lead time, paid failure, an analytical Bernoulli mean, discontinuous empirical ES, the book's exact 25-state aggregation, shared stress, portfolio-tail additivity, seeded reproduction, finite JSON output and invalid inputs. The HTTP integration suite also exercises the real simulation endpoint. Browser UI testing is a separate gate and was not requested.

Conceptual basis: Gleißner & Wolfrum (2019), [Risikoaggregation und Monte-Carlo-Simulation](https://doi.org/10.1007/978-3-658-24274-9). Method details: [NumPy random-stream compatibility](https://numpy.org/doc/stable/reference/random/compatibility.html), [SciPy binomial confidence intervals](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html), [Acerbi & Tasche on expected shortfall at discontinuities](https://arxiv.org/abs/cond-mat/0104295), and [Pyodide Web Worker execution](https://pyodide.org/en/0.28.3/usage/webworker.html). These references support methods, not the invented company inputs.

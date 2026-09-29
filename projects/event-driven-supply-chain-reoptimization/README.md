# Event-Driven Supply Chain Reoptimization

A compact decision-intelligence benchmark for converting supply-chain visibility events into operational reoptimization.

The project separates three layers that are often conflated in commercial "control tower" discussions:

1. **state visibility** — lane capacities, costs, demand and disruption events;
2. **decision logic** — a capacitated transshipment LP with explicit unmet-demand penalties;
3. **operational value** — cost, unmet demand and plan-instability comparisons against a frozen nominal plan.

The implementation is vendor-neutral. It does not reproduce FourKites, project44, Blue Yonder, Logility, IBM Sterling, or another commercial product.

## Research question

How much operational value comes from **visibility plus reoptimization**, rather than visibility alone?

For every event, the benchmark compares:

- **Frozen plan:** the nominal routing plan may contract when capacity disappears but may not expand onto previously unused lanes.
- **Event-driven reoptimization:** the complete current network state is optimized again after the event.

This creates a clean value-of-adaptation experiment.

## Model

For every lane `(i,j)`:

```text
0 <= x[i,j] <= current_capacity[i,j]
```

Source net outflow may not exceed available supply. Transshipment nodes conserve flow. Customer demand is balanced using explicit unmet-demand slack:

```text
inflow[c] - outflow[c] + unmet[c] = demand[c]
```

The objective is

```text
minimize
    sum(unit_cost[i,j] * x[i,j])
  + unmet_penalty * sum(unmet[c])
```

The unmet-demand variables keep the model diagnostically feasible during severe shocks; they are not a substitute for physical supply.

## Events

`DisruptionEvent` can change:

- lane capacity;
- lane unit cost;
- customer demand.

Events are cumulative, so the state after event `t` becomes the starting point for event `t+1`.

## KPI output

`run_control_tower` records:

- frozen-plan objective;
- reoptimized objective;
- frozen unmet demand;
- reoptimized unmet demand;
- reoptimized transport cost;
- L1 plan instability between consecutive reoptimized flow plans.

The final metric makes the usual service/cost improvement trade-off explicit: frequent reoptimization can improve economics while creating execution churn.

## Run

```bash
python -m pip install -e ".[dev]"
pytest
python examples/run_demo.py
```

## Scope

This is a synthetic research fixture, not a calibrated TMS/WMS/ERP implementation. It intentionally omits shipment lead-time state, inventory positioning, order-level commitments, integer fleet decisions, stochastic ETA models and multi-period recourse. Those are natural extensions once the event-to-decision interface is validated.

from __future__ import annotations

import json

from event_supply_chain import Arc, DisruptionEvent, NetworkState, run_control_tower


state = NetworkState(
    arcs=(
        Arc("S1", "DC1", 80, 1.0),
        Arc("S1", "DC2", 60, 2.4),
        Arc("S2", "DC1", 60, 1.8),
        Arc("S2", "DC2", 90, 1.2),
        Arc("DC1", "C1", 80, 1.0),
        Arc("DC1", "C2", 55, 1.1),
        Arc("DC2", "C1", 55, 1.3),
        Arc("DC2", "C2", 95, 1.0),
    ),
    supplies={"S1": 100, "S2": 100},
    demands={"C1": 70, "C2": 80},
    unmet_penalty=500.0,
)

events = [
    DisruptionEvent(
        "DC1-C2 lane disruption",
        capacity_multipliers={("DC1", "C2"): 0.10},
        cost_multipliers={("DC1", "C2"): 2.0},
    ),
    DisruptionEvent(
        "C2 demand spike",
        demand_multipliers={"C2": 1.20},
    ),
]

print(json.dumps(run_control_tower(state, events), indent=2))

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import linprog


@dataclass(frozen=True)
class Arc:
    origin: str
    destination: str
    capacity: float
    unit_cost: float
    transit_time: float = 1.0

    @property
    def key(self) -> tuple[str, str]:
        return (self.origin, self.destination)


@dataclass(frozen=True)
class NetworkState:
    arcs: tuple[Arc, ...]
    supplies: Mapping[str, float]
    demands: Mapping[str, float]
    unmet_penalty: float = 1_000.0

    @property
    def nodes(self) -> tuple[str, ...]:
        values = set(self.supplies) | set(self.demands)
        for arc in self.arcs:
            values.add(arc.origin)
            values.add(arc.destination)
        return tuple(sorted(values))


@dataclass(frozen=True)
class DisruptionEvent:
    name: str
    capacity_multipliers: Mapping[tuple[str, str], float] | None = None
    cost_multipliers: Mapping[tuple[str, str], float] | None = None
    demand_multipliers: Mapping[str, float] | None = None


@dataclass(frozen=True)
class PlanResult:
    objective: float
    transport_cost: float
    unmet_cost: float
    flows: Mapping[tuple[str, str], float]
    unmet: Mapping[str, float]

    @property
    def total_unmet(self) -> float:
        return float(sum(self.unmet.values()))


def _validate(state: NetworkState) -> None:
    if not state.arcs:
        raise ValueError("network must contain at least one arc")
    if state.unmet_penalty <= 0:
        raise ValueError("unmet_penalty must be positive")
    seen: set[tuple[str, str]] = set()
    for arc in state.arcs:
        if arc.capacity < 0 or arc.unit_cost < 0:
            raise ValueError("arc capacity and cost must be non-negative")
        if arc.key in seen:
            raise ValueError(f"duplicate arc: {arc.key}")
        seen.add(arc.key)
    if any(v < 0 for v in state.supplies.values()):
        raise ValueError("supplies must be non-negative")
    if any(v < 0 for v in state.demands.values()):
        raise ValueError("demands must be non-negative")


def solve_network(state: NetworkState) -> PlanResult:
    """Solve a capacitated transshipment LP with explicit unmet-demand slack."""
    _validate(state)
    arcs = list(state.arcs)
    demand_nodes = list(sorted(state.demands))
    n_arc = len(arcs)
    n_unmet = len(demand_nodes)

    c = np.array(
        [arc.unit_cost for arc in arcs]
        + [state.unmet_penalty for _ in demand_nodes],
        dtype=float,
    )
    bounds = [(0.0, arc.capacity) for arc in arcs] + [(0.0, None)] * n_unmet

    A_eq: list[list[float]] = []
    b_eq: list[float] = []

    for node in state.nodes:
        if node in state.supplies:
            continue
        row = [0.0] * (n_arc + n_unmet)
        for j, arc in enumerate(arcs):
            if arc.destination == node:
                row[j] += 1.0
            if arc.origin == node:
                row[j] -= 1.0
        if node in state.demands:
            row[n_arc + demand_nodes.index(node)] = 1.0
            rhs = float(state.demands[node])
        else:
            rhs = 0.0
        A_eq.append(row)
        b_eq.append(rhs)

    A_ub: list[list[float]] = []
    b_ub: list[float] = []
    for source, supply in sorted(state.supplies.items()):
        row = [0.0] * (n_arc + n_unmet)
        for j, arc in enumerate(arcs):
            if arc.origin == source:
                row[j] += 1.0
            if arc.destination == source:
                row[j] -= 1.0
        A_ub.append(row)
        b_ub.append(float(supply))

    result = linprog(
        c,
        A_ub=np.array(A_ub) if A_ub else None,
        b_ub=np.array(b_ub) if A_ub else None,
        A_eq=np.array(A_eq) if A_eq else None,
        b_eq=np.array(b_eq) if A_eq else None,
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(f"network optimization failed: {result.message}")

    flows = {arc.key: float(result.x[j]) for j, arc in enumerate(arcs)}
    unmet = {
        node: float(result.x[n_arc + i])
        for i, node in enumerate(demand_nodes)
    }
    transport_cost = float(sum(arc.unit_cost * flows[arc.key] for arc in arcs))
    unmet_cost = float(state.unmet_penalty * sum(unmet.values()))
    return PlanResult(
        objective=transport_cost + unmet_cost,
        transport_cost=transport_cost,
        unmet_cost=unmet_cost,
        flows=flows,
        unmet=unmet,
    )


def apply_event(state: NetworkState, event: DisruptionEvent) -> NetworkState:
    cap = event.capacity_multipliers or {}
    cost = event.cost_multipliers or {}
    demand = event.demand_multipliers or {}

    arcs = []
    for arc in state.arcs:
        cm = float(cap.get(arc.key, 1.0))
        km = float(cost.get(arc.key, 1.0))
        if cm < 0 or km < 0:
            raise ValueError("event multipliers must be non-negative")
        arcs.append(
            replace(
                arc,
                capacity=arc.capacity * cm,
                unit_cost=arc.unit_cost * km,
            )
        )

    demands = dict(state.demands)
    for node, multiplier in demand.items():
        if multiplier < 0:
            raise ValueError("demand multiplier must be non-negative")
        if node not in demands:
            raise KeyError(f"unknown demand node: {node}")
        demands[node] *= float(multiplier)

    return replace(state, arcs=tuple(arcs), demands=demands)


def evaluate_frozen_plan(state: NetworkState, nominal: PlanResult) -> PlanResult:
    """Evaluate a nominal plan after disruption without allowing lane expansion."""
    restricted = []
    for arc in state.arcs:
        approved = max(0.0, float(nominal.flows.get(arc.key, 0.0)))
        restricted.append(replace(arc, capacity=min(arc.capacity, approved)))
    return solve_network(replace(state, arcs=tuple(restricted)))


def _plan_instability(previous: PlanResult, current: PlanResult) -> float:
    keys = set(previous.flows) | set(current.flows)
    return float(sum(abs(current.flows.get(k, 0.0) - previous.flows.get(k, 0.0)) for k in keys))


def run_control_tower(
    initial_state: NetworkState,
    events: Sequence[DisruptionEvent],
) -> list[dict[str, float | str]]:
    """Run event-by-event frozen-plan and reoptimization comparisons."""
    nominal = solve_network(initial_state)
    state = initial_state
    previous_reoptimized = nominal
    rows: list[dict[str, float | str]] = []

    for event in events:
        state = apply_event(state, event)
        frozen = evaluate_frozen_plan(state, nominal)
        reoptimized = solve_network(state)
        rows.append(
            {
                "event": event.name,
                "frozen_objective": frozen.objective,
                "reoptimized_objective": reoptimized.objective,
                "frozen_unmet": frozen.total_unmet,
                "reoptimized_unmet": reoptimized.total_unmet,
                "reoptimized_transport_cost": reoptimized.transport_cost,
                "plan_instability": _plan_instability(previous_reoptimized, reoptimized),
            }
        )
        previous_reoptimized = reoptimized
    return rows

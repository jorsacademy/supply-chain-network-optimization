from event_supply_chain import (
    Arc,
    DisruptionEvent,
    NetworkState,
    apply_event,
    evaluate_frozen_plan,
    solve_network,
)


def sample_state() -> NetworkState:
    return NetworkState(
        arcs=(
            Arc("S1", "D1", 100, 1),
            Arc("S1", "D2", 100, 4),
            Arc("S2", "D1", 100, 4),
            Arc("S2", "D2", 100, 1),
            Arc("D1", "C1", 100, 1),
            Arc("D1", "C2", 100, 1),
            Arc("D2", "C1", 100, 1),
            Arc("D2", "C2", 100, 1),
        ),
        supplies={"S1": 100, "S2": 100},
        demands={"C1": 80, "C2": 80},
        unmet_penalty=1000,
    )


def test_solution_satisfies_demand_without_unmet():
    result = solve_network(sample_state())
    assert result.total_unmet < 1e-8
    assert result.objective > 0


def test_disruption_reoptimization_dominates_frozen_plan():
    state = sample_state()
    nominal = solve_network(state)
    disrupted = apply_event(
        state,
        DisruptionEvent(
            "cut a preferred downstream lane",
            capacity_multipliers={("D1", "C2"): 0.0},
        ),
    )
    frozen = evaluate_frozen_plan(disrupted, nominal)
    reoptimized = solve_network(disrupted)
    assert reoptimized.total_unmet <= frozen.total_unmet + 1e-8
    assert reoptimized.objective <= frozen.objective + 1e-8


def test_event_updates_capacity_and_demand():
    state = sample_state()
    changed = apply_event(
        state,
        DisruptionEvent(
            "shock",
            capacity_multipliers={("S1", "D1"): 0.5},
            demand_multipliers={"C1": 1.25},
        ),
    )
    lane = next(a for a in changed.arcs if a.key == ("S1", "D1"))
    assert lane.capacity == 50
    assert changed.demands["C1"] == 100

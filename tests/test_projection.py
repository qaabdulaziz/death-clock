from datetime import date

import pytest

from app.projection import add_months, calculate_projection, completed_months


def settings(**overrides):
    values = {
        "date_of_birth": "2000-01-15",
        "life_expectancy_years": 2.0,
        "starting_balance": 0.0,
        "monthly_contribution": 100.0,
        "annual_return_rate": 0.0,
        "currency": "USD",
        "setup_complete": True,
    }
    values.update(overrides)
    return values


def test_add_months_clamps_to_valid_day():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)


def test_completed_months_respects_clamped_month_end_anniversaries():
    assert completed_months(date(2000, 1, 31), date(2000, 2, 29)) == 1
    assert completed_months(date(2000, 1, 15), date(2000, 3, 10)) == 1


def test_projection_reports_grid_metadata_and_monthly_balances():
    result = calculate_projection(settings(), [], today=date(2000, 3, 10))

    assert result["metadata"] == {
        "birth_date": "2000-01-15",
        "end_date": "2002-01-15",
        "total_months": 24,
        "months_lived": 1,
        "months_remaining": 23,
        "current_age_years": 0,
        "current_age_months": 1,
        "current_month_index": 2,
    }
    assert result["balances"][0] == {"month": "2000-03", "balance": 100.0}
    assert result["balances"][-1] == {"month": "2001-12", "balance": 2200.0}


def test_projects_trigger_cheapest_first_with_sequential_deduction():
    projects = [
        {"id": 1, "name": "A", "cost": 250.0},
        {"id": 2, "name": "B", "cost": 100.0},
        {"id": 3, "name": "C", "cost": 100.0},
    ]

    result = calculate_projection(settings(), projects, today=date(2000, 1, 15))
    starts = {project["id"]: project for project in result["projects"]}

    assert starts[2]["start_month"] == "2000-01"
    assert starts[3]["start_month"] == "2000-02"
    assert starts[1]["start_month"] == "2000-05"
    assert result["balances"][4]["balance"] == pytest.approx(50.0)


def test_multiple_projects_can_trigger_in_one_month():
    projects = [
        {"id": 1, "name": "A", "cost": 40.0},
        {"id": 2, "name": "B", "cost": 60.0},
    ]
    result = calculate_projection(settings(monthly_contribution=100.0), projects, today=date(2000, 1, 15))

    assert [project["start_month"] for project in result["projects"]] == ["2000-01", "2000-01"]
    assert result["balances"][0]["balance"] == pytest.approx(0.0)


def test_unreachable_projects_are_flagged():
    result = calculate_projection(
        settings(starting_balance=0, monthly_contribution=0),
        [{"id": 9, "name": "A", "cost": 1.0}],
        today=date(2000, 1, 15),
    )

    project = result["projects"][0]
    assert project["start_month"] is None
    assert project["status"] == "not reachable within projected lifetime"


def test_return_compounds_before_contribution():
    result = calculate_projection(
        settings(starting_balance=1200.0, monthly_contribution=10.0, annual_return_rate=12.0),
        [],
        today=date(2000, 1, 15),
    )
    assert result["balances"][0]["balance"] == pytest.approx(1222.0)


def test_project_age_uses_completed_months_at_start_of_calendar_month():
    result = calculate_projection(
        settings(monthly_contribution=100.0),
        [{"id": 1, "name": "A", "cost": 200.0}],
        today=date(2000, 1, 15),
    )
    project = result["projects"][0]
    assert project["start_month"] == "2000-02"
    assert (project["start_age_years"], project["start_age_months"]) == (0, 0)


def test_future_birth_date_and_expired_lifetime_do_not_crash():
    future = calculate_projection(
        settings(date_of_birth="2030-01-15", life_expectancy_years=1),
        [{"id": 1, "name": "A", "cost": 100.0}],
        today=date(2029, 1, 1),
    )
    expired = calculate_projection(
        settings(date_of_birth="2000-01-01", life_expectancy_years=1),
        [],
        today=date(2002, 1, 1),
    )

    assert future["metadata"]["months_lived"] == 0
    assert future["metadata"]["current_month_index"] == -12
    assert future["balances"][0]["month"] == "2030-02"
    assert future["projects"][0]["start_month"] == "2030-02"
    assert expired["metadata"]["months_remaining"] == 0
    assert expired["balances"] == []

"""Life timeline and financial feasibility calculations."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any


def add_months(value: date, months: int) -> date:
    """Return ``value`` shifted by whole calendar months, clamping its day.

    Month arithmetic is used instead of fixed day counts so the life grid and
    financial timeline remain aligned to real calendar months.
    """

    absolute_month = value.year * 12 + (value.month - 1) + months
    year, zero_based_month = divmod(absolute_month, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_difference(start: date, end: date) -> int:
    """Return whole calendar-month boundaries between two dates' months."""

    return (end.year - start.year) * 12 + end.month - start.month


def completed_months(start: date, end: date) -> int:
    """Return completed calendar months using clamped month anniversaries.

    For month-end dates, the last valid day is the anniversary: January 31
    through February 29 in a leap year is one completed month.
    """

    if end < start:
        return 0
    months = month_difference(start, end)
    if add_months(start, months) > end:
        months -= 1
    return max(0, months)


def calculate_projection(
    settings: dict[str, Any], projects: list[dict[str, Any]], today: date | None = None
) -> dict[str, Any]:
    """Project balances and determine project start months.

    Each projected month first applies ``balance * (1 + monthly_rate)`` and
    then adds the monthly contribution. The engine repeatedly funds the
    cheapest remaining affordable project, deducting its full cost before
    checking the next project. This greedy, sequential depletion means an
    earlier project genuinely delays later projects. Projects that cannot be
    fully funded before the configured end of life remain unreachable.
    """

    today = today or date.today()
    birth_date = date.fromisoformat(str(settings["date_of_birth"]))
    total_months = max(0, round(float(settings["life_expectancy_years"]) * 12))
    end_date = add_months(birth_date, total_months)
    current_index = month_difference(birth_date, today)
    completed_age_months = completed_months(birth_date, today)
    months_lived = min(total_months, completed_age_months)
    months_remaining = max(0, total_months - months_lived)
    age_years, age_months = divmod(completed_age_months, 12)

    metadata = {
        "birth_date": birth_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_months": total_months,
        "months_lived": months_lived,
        "months_remaining": months_remaining,
        "current_age_years": age_years,
        "current_age_months": age_months,
        "current_month_index": current_index,
    }

    current_month = today.replace(day=1)
    projection_start = current_month
    if today < birth_date:
        projection_start = birth_date.replace(day=1)
        if birth_date.day > 1:
            projection_start = add_months(projection_start, 1)
    end_month = end_date.replace(day=1)
    timeline_length = max(0, month_difference(projection_start, end_month))
    monthly_rate = (float(settings["annual_return_rate"]) / 100.0) / 12.0
    contribution = float(settings["monthly_contribution"])
    balance = float(settings["starting_balance"])

    remaining = sorted(
        (dict(project) for project in projects),
        key=lambda project: (float(project["cost"]), int(project["id"])),
    )
    starts: dict[int, str] = {}
    balances: list[dict[str, Any]] = []

    for offset in range(timeline_length):
        month = add_months(projection_start, offset)
        balance = balance * (1.0 + monthly_rate) + contribution
        while remaining and balance + 1e-9 >= float(remaining[0]["cost"]):
            project = remaining.pop(0)
            balance -= float(project["cost"])
            if abs(balance) < 1e-9:
                balance = 0.0
            starts[int(project["id"])] = month.strftime("%Y-%m")
        balances.append({"month": month.strftime("%Y-%m"), "balance": round(balance, 2)})

    computed_projects = []
    for project in projects:
        project_id = int(project["id"])
        start_month = starts.get(project_id)
        result = {
            "id": project_id,
            "name": project["name"],
            "cost": float(project["cost"]),
            "start_month": start_month,
            "start_age_years": None,
            "start_age_months": None,
            "months_away": None,
            "status": "not reachable within projected lifetime",
        }
        if start_month:
            start_date = date.fromisoformat(f"{start_month}-01")
            completed_start_months = completed_months(birth_date, start_date)
            start_age_years, start_age_months = divmod(completed_start_months, 12)
            result.update(
                {
                    "start_age_years": start_age_years,
                    "start_age_months": start_age_months,
                    "months_away": max(0, month_difference(current_month, start_date)),
                    "status": "reachable",
                }
            )
        computed_projects.append(result)

    return {"metadata": metadata, "balances": balances, "projects": computed_projects}

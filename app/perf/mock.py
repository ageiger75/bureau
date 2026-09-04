"""Mock performance data (brief §24, §25).

Entirely invented. No real L'OCCITANE figure, market, person or product appears here.

The dataset is built to exercise the cockpit rather than to flatter it: a large market
whose action plan targets the wrong driver, a market with strong traffic and weak
conversion, a forecast revised down three months running, one genuine outperformance, and
commitments in every state including one that was delivered and produced nothing.

Sales are never written down directly — they are the product of the drivers. A scenario
therefore cannot claim a sales figure its own drivers do not support.
"""

from __future__ import annotations

from typing import List, Optional

from ..domain.commitments import CommitmentInput
from ..domain.enums import CommitmentStatus
from ..util import days_until, today
from .kpi import (
    ANNUAL,
    DOWN,
    LOCKED,
    MONTHLY,
    P1,
    P2,
    PROVISIONAL,
    QUARTERLY,
    Kpi,
    Reading,
)
from .history import Ytd
from .model import (
    ECOMMERCE,
    NO_COUNTER_REASON,
    RETAIL,
    BusinessUnit,
    Dataset,
    Drivers,
    Owner,
    retail_drivers,
)


def _ecom(sales: float, conversion: float, aov: float) -> Drivers:
    """Digital drivers for a target sales figure.

    Sessions are derived, not typed in: sales = sessions × conversion × AOV must hold
    exactly, and a dataset where the two disagree would discredit every diagnosis built
    on top of it.
    """
    sessions = sales / (conversion * aov)
    return Drivers(("Sessions", "Conversion", "AOV"), (sessions, conversion, aov))


def _retail(sales: float, conversion: float, upt: float, asp: float) -> Drivers:
    """Retail drivers for a target sales figure. Traffic is derived, for the same reason."""
    traffic = sales / (conversion * upt * asp)
    return Drivers(("Traffic", "Conversion", "UPT", "ASP"), (traffic, conversion, upt, asp))


def _in_days(offset: int) -> str:
    from datetime import timedelta

    return (today() + timedelta(days=offset)).isoformat()


# --------------------------------------------------------------------------- owners

NAOKI = Owner("Naoki", "Managing Director", "Japan")
JULIEN = Owner("Julien", "Regional Director", "Europe")
YANN = Owner("Yann", "Managing Director", "US")
SOFIA = Owner("Sofia", "E-commerce Director", "Germany")
MARCO = Owner("Marco", "Managing Director", "Italy")


def units() -> List[BusinessUnit]:
    """Seven business units, sized so the group total is a real number.

    Each is written as a target sales figure plus the rates that produced it; volume is
    derived. The scenarios of brief §25 are all here, and one — Italy — is deliberately
    too small to matter, so the materiality floor can be seen doing its job.
    """
    return [
        # -- Japan: the flagship problem. Traffic holds, conversion collapses, and the
        #    recovery plan targets acquisition — the one thing the data exonerates.
        BusinessUnit(
            key="japan-ecom",
            label="Japan E-commerce",
            market="Japan",
            region="Asia",
            channel=ECOMMERCE,
            owner=NAOKI,
            actual=_ecom(5_400_000, 0.01745, 62.60),
            budget=_ecom(6_600_000, 0.02100, 62.00),
            last_year=_ecom(6_590_000, 0.02080, 61.20),
            forecast_sales=5_350_000,
            strategic_weight=1.2,
            months_below_budget=3,
            gap_history=(-410_000, -780_000, -1_200_000),
            forecast_history=(6_600_000, 6_100_000, 5_350_000),
            market_index_pct=-0.04,
            management_explanation="Sales are down because the market is difficult.",
            action_focus="Sessions",
        ),
        # -- France retail: traffic up strongly, sales barely up on last year, conversion
        #    below it. A fire and an opportunity at once — they are the same fact.
        BusinessUnit(
            key="france-retail",
            label="France Retail",
            market="France",
            region="Europe",
            channel=RETAIL,
            owner=JULIEN,
            actual=_retail(17_600_000, 0.11751, 2.10, 47.50),
            budget=_retail(18_400_000, 0.12900, 2.12, 48.00),
            last_year=_retail(17_450_000, 0.12750, 2.09, 47.10),
            forecast_sales=18_100_000,
            strategic_weight=1.1,
            months_below_budget=2,
            gap_history=(-520_000, -800_000),
            market_index_pct=0.010,
            action_focus="Traffic",
        ),
        # -- Japan retail: a market without reliable footfall counters. The gap is as
        #    real as any other; its cause simply cannot be read, and the screen says which
        #    of the two it is. Built through `retail_drivers`, which refuses to produce a
        #    conversion rate here whatever it is handed.
        BusinessUnit(
            key="japan-retail",
            label="Japan Retail",
            market="Japan",
            region="Asia",
            channel=RETAIL,
            owner=NAOKI,
            actual=retail_drivers("Japan", 8_900_000),
            budget=retail_drivers("Japan", 9_600_000),
            last_year=retail_drivers("Japan", 9_250_000),
            forecast_sales=9_100_000,
            months_below_budget=2,
            gap_history=(-450_000, -700_000),
            # A plan asking for growth the record has never shown. Kept on a unit with no
            # action focus of its own, so the demonstration screen carries both kinds of
            # question — one about where the plan aims, one about whether it was reachable.
            plan_vs_record=(
                "The plan asks for +18%, where the last twelve months delivered +2% and "
                "the last three months ran at -4% — the plan is above every reading of "
                "the record, by up to 22 points — €4.1m across the year's plan, beside "
                "a monthly gap of its own. The business is slowing down, which argues "
                "against it."
            ),
            no_breakdown_reason=NO_COUNTER_REASON,
        ),
        # -- China: the traffic problem (brief §24). Conversion is steady; the sessions
        #    simply are not there. A different diagnosis needs a different conversation.
        BusinessUnit(
            key="china-ecom",
            label="China E-commerce",
            market="China",
            region="Asia",
            channel=ECOMMERCE,
            owner=NAOKI,
            actual=_ecom(2_300_000, 0.02180, 55.50),
            budget=_ecom(3_200_000, 0.02200, 55.00),
            last_year=_ecom(3_050_000, 0.02190, 54.20),
            forecast_sales=2_450_000,
            months_below_budget=2,
            gap_history=(-640_000, -900_000),
            action_focus="Conversion",
        ),
        # -- UK: a moderate miss, but the forecast has been cut three months running.
        #    The credibility of the number is the issue, not only the number.
        BusinessUnit(
            key="uk-retail",
            label="UK Retail",
            market="United Kingdom",
            region="Europe",
            channel=RETAIL,
            owner=JULIEN,
            actual=_retail(6_800_000, 0.12100, 1.98, 44.00),
            budget=_retail(7_300_000, 0.12500, 2.02, 44.50),
            last_year=_retail(7_000_000, 0.12400, 2.00, 44.20),
            forecast_sales=7_100_000,
            months_below_budget=4,
            gap_history=(-300_000, -420_000, -500_000),
            forecast_history=(8_400_000, 7_900_000, 7_450_000, 7_100_000),
        ),
        # -- Germany: conversion below last year with traffic flat. A recoverable gap,
        #    too small to be a fire and large enough to be an opportunity.
        BusinessUnit(
            key="germany-ecom",
            label="Germany E-commerce",
            market="Germany",
            region="Europe",
            channel=ECOMMERCE,
            owner=SOFIA,
            actual=_ecom(1_770_000, 0.02150, 58.00),
            budget=_ecom(1_900_000, 0.02300, 58.50),
            last_year=_ecom(1_940_000, 0.02420, 57.40),
            forecast_sales=1_850_000,
            months_below_budget=1,
            gap_history=(-90_000, -130_000),
        ),
        # -- US retail: the outperformance. Something works and nobody has asked why.
        BusinessUnit(
            key="us-retail",
            label="US Retail",
            market="United States",
            region="Americas",
            channel=RETAIL,
            owner=YANN,
            actual=_retail(5_000_000, 0.14200, 2.46, 52.00),
            budget=_retail(4_390_000, 0.13500, 2.30, 51.00),
            last_year=_retail(4_240_000, 0.13300, 2.28, 50.20),
            forecast_sales=5_100_000,
            months_below_budget=0,
            gap_history=(310_000, 540_000),
            win_driver="Almond bundles paired with in-store demonstration",
        ),
        # -- Italy: a small miss, below the materiality floor. Present in the data, absent
        #    from the screen — a -1.2% variance on a small market is not CEO work.
        BusinessUnit(
            key="italy-retail",
            label="Italy Retail",
            market="Italy",
            region="Europe",
            channel=RETAIL,
            owner=MARCO,
            actual=_retail(4_550_000, 0.12400, 1.95, 45.00),
            budget=_retail(4_600_000, 0.12450, 1.96, 45.10),
            last_year=_retail(4_500_000, 0.12300, 1.94, 44.60),
            forecast_sales=4_600_000,
            months_below_budget=1,
            gap_history=(-30_000, -50_000),
        ),
        # -- Finland: nothing recorded this month against a real last year, with sessions
        #    still arriving. Observed in the live data. A collapse would show in the
        #    traffic too; a broken feed shows exactly like this.
        BusinessUnit(
            key="finland-ecom",
            label="Finland E-commerce",
            market="Finland",
            region="Europe",
            channel=ECOMMERCE,
            owner=SOFIA,
            actual=Drivers.sales_only(0.0),
            budget=Drivers.sales_only(9_000.0),
            last_year=Drivers.sales_only(8_361.0),
            forecast_sales=9_000.0,
            sessions=4_712.0,
            orders=0.0,
        ),
        # -- Hong Kong: heavy traffic, real revenue, and no orders recorded against it.
        #    The business is there; the transactional tracking is not.
        BusinessUnit(
            key="hongkong-ecom",
            label="Hong Kong E-commerce",
            market="Hong Kong",
            region="Asia",
            channel=ECOMMERCE,
            owner=NAOKI,
            actual=Drivers.sales_only(51_000.0),
            budget=Drivers.sales_only(1_200_000.0),
            last_year=Drivers.sales_only(900_000.0),
            forecast_sales=200_000.0,
            sessions=686_994.0,
            orders=0.0,
        ),
        # -- Rest of World: aggregated and close to plan. It exists so the header reflects
        #    the whole business rather than the markets that happen to be interesting.
        BusinessUnit(
            key="row",
            label="Rest of World",
            market="Rest of World",
            region="Rest of World",
            channel=RETAIL,
            owner=Owner("Regional teams", "Various", "Rest of World"),
            actual=_retail(101_300_000, 0.12650, 2.05, 45.60),
            budget=_retail(101_700_000, 0.12680, 2.05, 45.50),
            last_year=_retail(100_900_000, 0.12600, 2.04, 45.00),
            forecast_sales=102_000_000,
            months_below_budget=0,
            gap_history=(120_000, -400_000),
            is_aggregate=True,
        ),
    ]


def dataset() -> Dataset:
    return Dataset(
        period_label="Sales MTD",
        as_of=today().isoformat(),
        units=units(),
        # Invented like everything else here, but present: a block that only ever renders
        # against the warehouse is a block nobody looks at until it is wrong in front of
        # the person it was built for. The unmatched amounts are included on purpose —
        # they are the part of the year to date that is easy to get wrong.
        ytd=Ytd(
            label="FY27 to date",
            first_period="2026-04",
            last_period="2026-07",
            actual=41_800_000.0,
            budget=44_300_000.0,
            unbudgeted_actual=2_100_000.0,
            unsold_budget=640_000.0,
            unbudgeted_lines=14,
            unsold_lines=6,
            months=4,
            zero_goal_actual=780_000.0,
            zero_goal_lines=5,
            plan_source="the planning workbook",
        ),
    )


# --------------------------------------------------------------------- commitments


class MockCommitment:
    """A commitment as the cockpit needs it (brief §17).

    Four fields beyond what Decision Room stores — market, issue, expected and actual
    impact — because the loop the cockpit closes is `problem → action → result`, and the
    result is worthless without the expectation it is measured against.
    """

    __slots__ = (
        "owner_name",
        "market",
        "issue",
        "action",
        "expected_impact",
        "actual_impact",
        "due_date",
        "status",
        "is_critical",
        "evidence",
        "postponements",
        "notes",
    )

    def __init__(
        self,
        owner_name: str,
        market: str,
        issue: str,
        action: str,
        expected_impact: str,
        due_date: Optional[str],
        status: str,
        actual_impact: str = "",
        is_critical: bool = False,
        evidence: str = "",
        postponements: int = 0,
        notes: str = "",
    ) -> None:
        self.owner_name = owner_name
        self.market = market
        self.issue = issue
        self.action = action
        self.expected_impact = expected_impact
        self.actual_impact = actual_impact
        self.due_date = due_date
        self.status = status
        self.is_critical = is_critical
        self.evidence = evidence
        self.postponements = postponements
        self.notes = notes

    def as_input(self) -> CommitmentInput:
        """Bridge to the commitment rules already written for Decision Room."""
        return CommitmentInput(
            action=self.action,
            owner_name=self.owner_name,
            due_date=self.due_date,
            status=self.status,
            is_critical=self.is_critical,
            evidence=self.evidence,
        )

    @property
    def days_left(self) -> Optional[int]:
        return days_until(self.due_date)


def commitments() -> List[MockCommitment]:
    OPEN = CommitmentStatus.OPEN.value
    IN_PROGRESS = CommitmentStatus.IN_PROGRESS.value
    DONE = CommitmentStatus.DONE.value
    BLOCKED = CommitmentStatus.BLOCKED.value

    return [
        MockCommitment(
            owner_name="Naoki",
            market="Japan",
            issue="Mobile conversion down 17% against plan",
            action="Ship the mobile checkout recovery plan",
            expected_impact="+€400k/month",
            due_date=_in_days(-6),
            status=OPEN,
            is_critical=True,
            postponements=2,
            notes="Moved twice. Still the largest single driver of the Japan gap.",
        ),
        MockCommitment(
            owner_name="Naoki",
            market="Japan",
            issue="Paid acquisition below plan",
            action="Increase paid search investment by 15%",
            expected_impact="",
            due_date=_in_days(4),
            status=IN_PROGRESS,
            notes="No quantified impact. Targets traffic, which the data does not blame.",
        ),
        MockCommitment(
            owner_name="Julien",
            market="France",
            issue="Store conversion below last year despite traffic growth",
            action="Run the conversion clinic in the 20 largest stores",
            expected_impact="+€420k/month",
            due_date=_in_days(-2),
            status=BLOCKED,
            is_critical=True,
            postponements=1,
            evidence="Blocked on field training capacity.",
        ),
        MockCommitment(
            owner_name="Sofia",
            market="Germany",
            issue="Mobile site search returning poor results",
            action="Improve mobile search relevance",
            expected_impact="+€180k/month",
            actual_impact="No measurable uplift after three weeks",
            due_date=_in_days(-21),
            status=DONE,
            evidence="Shipped on time. Conversion unchanged since release.",
            notes="Delivered, and it did not work. The issue is still open.",
        ),
        MockCommitment(
            owner_name="Yann",
            market="United States",
            issue="Bundle mechanic underused outside pilot stores",
            action="Roll out the Almond bundle to all US doors",
            expected_impact="+€250k/month",
            actual_impact="≈ +€310k/month",
            due_date=_in_days(-30),
            status=DONE,
            evidence="Rollout completed. Incremental performance above expectation.",
        ),
        MockCommitment(
            owner_name="Julien",
            market="United Kingdom",
            issue="Forecast revised down three months running",
            action="Rebuild the UK forecast bottom-up with store-level input",
            expected_impact="Forecast accuracy within ±3%",
            due_date=_in_days(9),
            status=OPEN,
            is_critical=True,
        ),
        MockCommitment(
            owner_name="Sofia",
            market="Germany",
            issue="CRM reactivation not running",
            action="Relaunch the lapsed-customer CRM programme",
            expected_impact="+€250k/month",
            due_date=_in_days(16),
            status=OPEN,
        ),
        MockCommitment(
            owner_name="Naoki",
            market="Japan",
            issue="Mobile PDP to add-to-cart step deteriorating",
            action="Rebuild the mobile product page add-to-cart flow",
            expected_impact="+€300k/month",
            due_date=_in_days(27),
            status=OPEN,
            is_critical=True,
        ),
        MockCommitment(
            owner_name="Julien",
            market="France",
            issue="Store staffing below plan at weekends",
            action="Close the weekend staffing gap in the 30 busiest stores",
            expected_impact="+€150k/month",
            due_date=_in_days(3),
            status=IN_PROGRESS,
        ),
        MockCommitment(
            owner_name="Yann",
            market="United States",
            issue="Bundle mechanic not yet tested in Europe",
            action="Document the Almond bundle playbook for European markets",
            expected_impact="Enables replication decision",
            due_date=_in_days(12),
            status=OPEN,
        ),
        MockCommitment(
            owner_name="Sofia",
            market="Germany",
            issue="Checkout abandonment above benchmark on mobile",
            action="Add express payment options at checkout",
            expected_impact="+€120k/month",
            due_date=_in_days(-4),
            status=OPEN,
            postponements=1,
        ),
        MockCommitment(
            owner_name="Marco",
            market="Italy",
            issue="Assortment gaps in the top 30 stores",
            action="Close the assortment gaps identified in the January audit",
            expected_impact="+€90k/month",
            due_date=_in_days(21),
            status=IN_PROGRESS,
        ),
    ]


# --------------------------------------------------------------------- client KPIs

#: Customer KPIs (brief follow-up: recruitment, ARC, and the rest of the tracker).
#:
#: The taxonomy is real — recruitment, active customers, average transaction value, NPS,
#: lifetime value, retail turnover — because that is what has to be monitored. Every
#: value, target and owner below is invented, as everywhere else in this file.
#:
#: The set is chosen to exercise the three reading rules rather than to look complete:
#: one KPI where lower is better, one reported quarterly, one whose definition is not
#: settled, and one genuinely late.


def client_kpis() -> List[Kpi]:
    return [
        # -- Recruitment. Japan is the market already on fire for conversion; its
        #    recruitment is falling too, which is a different conversation from a
        #    checkout problem.
        Kpi(
            key="japan-new-customers",
            label="New customers",
            definition="Growth in newly recruited customers vs last year",
            scope="Japan",
            owner="Naoki",
            pillar="Client Acquisition",
            unit="%",
            target=5.0,
            frequency=MONTHLY,
            source="CRM",
            priority=P1,
            last_year=6.2,
            readings=[
                Reading("2026-05", 2.1),
                Reading("2026-06", 0.4),
                Reading("2026-07", -1.8),
            ],
        ),
        Kpi(
            key="japan-arc",
            label="ARC — active customers",
            definition="Customers with at least one purchase in the last 12 months",
            scope="Japan",
            owner="Naoki",
            pillar="Client Acquisition",
            unit="k clients",
            target=980.0,
            frequency=MONTHLY,
            source="CRM",
            priority=P1,
            last_year=968.0,
            readings=[
                Reading("2026-05", 962.0),
                Reading("2026-06", 951.0),
                Reading("2026-07", 944.0),
            ],
        ),
        # -- France: recruitment is working. The problem there is conversion in store,
        #    not the top of the funnel — and the KPIs should say so plainly.
        Kpi(
            key="france-new-customers",
            label="New customers",
            definition="Growth in newly recruited customers vs last year",
            scope="France",
            owner="Julien",
            pillar="Client Acquisition",
            unit="%",
            target=4.0,
            frequency=MONTHLY,
            source="CRM",
            priority=P1,
            last_year=3.1,
            readings=[
                Reading("2026-05", 5.9),
                Reading("2026-06", 6.8),
                Reading("2026-07", 7.4),
            ],
        ),
        Kpi(
            key="france-atv",
            label="ATV — average transaction value",
            definition="Average basket, growth vs last year",
            scope="France",
            owner="Julien",
            pillar="Client Acquisition",
            unit="%",
            target=2.0,
            frequency=MONTHLY,
            source="Revenue / RGM",
            priority=P2,
            last_year=1.4,
            readings=[
                Reading("2026-06", 1.2),
                Reading("2026-07", 0.9),
            ],
        ),
        # -- Lower is better. A single sign convention has to hold across the cockpit,
        #    or a reader learns to check the direction before trusting a colour.
        Kpi(
            key="france-turnover",
            label="Retail turnover — voluntary",
            definition="Voluntary departures, rolling 12 months",
            scope="France",
            owner="People",
            pillar="3P People",
            unit="%",
            target=20.0,
            direction=DOWN,
            frequency=MONTHLY,
            source="HR",
            priority=P2,
            last_year=21.5,
            readings=[
                Reading("2026-06", 23.4),
                Reading("2026-07", 24.1),
            ],
        ),
        # -- Quarterly. In the middle of Q2 there is no August figure, and saying so is
        #    the calendar rather than an alert.
        Kpi(
            key="us-nps",
            label="NPS",
            definition="VOC framework, market score",
            scope="United States",
            owner="Yann",
            pillar="Brand Elevation",
            unit="score",
            target=76.0,
            frequency=QUARTERLY,
            source="VOC",
            priority=P1,
            last_year=71.0,
            readings=[Reading("Q1 FY27", 78.0)],
        ),
        # -- Definition not settled. The variance is shown; the challenge is withheld,
        #    with the reason, so nobody is sent to argue about an unagreed number.
        Kpi(
            key="japan-nps",
            label="NPS",
            definition="VOC framework — Asia methodology being aligned",
            scope="Japan",
            owner="Naoki",
            pillar="Brand Elevation",
            unit="score",
            target=74.0,
            frequency=QUARTERLY,
            source="VOC",
            definition_status=PROVISIONAL,
            priority=P1,
            last_year=70.0,
            readings=[Reading("Q1 FY27", 68.0)],
            open_question=(
                "the Asia scoring method is not yet aligned with the one used in China, "
                "so the two are not comparable"
            ),
        ),
        # -- Genuinely late: quarterly, and the closed quarter was never reported.
        Kpi(
            key="germany-clv",
            label="CLV — top customers",
            definition="Average lifetime value of the top decile",
            scope="Germany",
            owner="Sofia",
            pillar="Client Acquisition",
            unit="€",
            target=420.0,
            frequency=QUARTERLY,
            source="CRM",
            priority=P2,
            last_year=398.0,
            readings=[Reading("Q4 FY26", 402.0)],
        ),
        Kpi(
            key="us-new-customers",
            label="New customers",
            definition="Growth in newly recruited customers vs last year",
            scope="United States",
            owner="Yann",
            pillar="Client Acquisition",
            unit="%",
            target=6.0,
            frequency=MONTHLY,
            source="CRM",
            priority=P1,
            last_year=8.0,
            readings=[
                Reading("2026-05", 9.8),
                Reading("2026-06", 11.2),
                Reading("2026-07", 12.6),
            ],
        ),
        # A green group figure with red markets underneath. Present in the mock for the
        # same reason as the rest: the shape that only ever renders against the warehouse
        # is the shape nobody looks at until it is wrong.
        _behind(
            Kpi(
                key="group-upt",
                label="Units per transaction",
                definition="Articles sold per till receipt",
                scope="Group",
                owner="Retail",
                pillar="Retail Excellence",
                unit="units",
                target=3.0,
                frequency=MONTHLY,
                source="Sell-out",
                priority=P2,
                readings=[
                    Reading("2026-05", 3.42),
                    Reading("2026-06", 3.55),
                    Reading("2026-07", 3.49),
                ],
            ),
            22,
            [("Finland", 2.11), ("Italy", 2.46), ("Germany", 2.71),
             ("United Kingdom", 2.90)],
        ),
        Kpi(
            key="group-ntb",
            label="Net NTB acquisition",
            definition="Net new-to-brand customers across all markets",
            scope="Group",
            owner="Revenue",
            pillar="Client Acquisition",
            unit="k clients",
            target=310.0,
            frequency=MONTHLY,
            source="CRM",
            priority=P1,
            last_year=298.0,
            readings=[
                Reading("2026-05", 302.0),
                Reading("2026-06", 297.0),
                Reading("2026-07", 291.0),
            ],
        ),
    ]


def bulk_findings() -> List:
    """Two markets where the bulk hides what the shoppers are doing.

    Invented like the rest of this module, and present for the same reason as the year to
    date above: a block that only ever renders against the warehouse is a block nobody
    looks at until it is wrong, in front of the person it was built for.
    """
    from . import bulk as bulk_module

    window = ("2026-04", "2026-05", "2026-06")
    return [
        # Bulk down, and the total is the only place it shows. Retail is holding.
        bulk_module.MarketBulk("China", window,
                               sales=52_000_000.0, ex_bulk=48_600_000.0,
                               sales_before=55_400_000.0, ex_bulk_before=48_100_000.0,
                               comparable=True),
        # A sixth of the market, and it moved the wrong way for the shoppers.
        bulk_module.MarketBulk("Hong Kong", window,
                               sales=14_200_000.0, ex_bulk=11_700_000.0,
                               sales_before=13_300_000.0, ex_bulk_before=12_400_000.0,
                               comparable=True),
    ]


def _behind(kpi, markets_read, behind):
    """A KPI plus the markets its group figure is hiding.

    Set after construction rather than passed in: the readings carry it in the real
    join, and adding a constructor argument for the mock's convenience would put the
    mock's shape into the model.
    """
    kpi.markets_read = markets_read
    kpi.behind = list(behind)
    return kpi


def month_to_date() -> List[dict]:
    """Le mois en cours, inventé : trois marchés, lus jusqu'au 17."""
    import datetime

    today = datetime.date.today()
    through = today.replace(day=min(17, today.day)).isoformat()
    return [
        {"market": "JAPAN", "iso2": "JP", "sales_to_date": 2_150_000.0, "read_through": through},
        {"market": "FRANCE", "iso2": "FR", "sales_to_date": 1_310_000.0, "read_through": through},
        {"market": "CHINA", "iso2": "CN", "sales_to_date": 3_020_000.0, "read_through": through},
    ]


def month_targets(period: str) -> dict:
    return {"Japan": 4_000_000.0, "France": 2_400_000.0, "China": 6_500_000.0}

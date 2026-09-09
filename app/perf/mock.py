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

from typing import Dict, List, Optional

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
from .analytics import format_eur
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
                "Le plan demande +18 %%, là où les douze derniers mois ont livré +2 %% et les "
                "trois derniers mois ont fait -4 %% — au-dessus de chaque lecture du réalisé, "
                "jusqu'à 22 points d'écart. %s embarqués sur l'année. Le business ralentit, "
                "ce qui plaide contre." % format_eur(4_100_000)
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
        #    from the screen — a one-point variance on a small market is not CEO work.
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
        period=today().strftime("%Y-%m"),
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
        {"market": "JAPAN", "iso2": "JP", "sales_to_date": 2_150_000.0,
         "read_through": through, "first_day_sales": 140_000.0},
        {"market": "FRANCE", "iso2": "FR", "sales_to_date": 1_310_000.0,
         "read_through": through, "first_day_sales": 80_000.0},
        {"market": "CHINA", "iso2": "CN", "sales_to_date": 3_020_000.0,
         "read_through": through, "first_day_sales": 2_100_000.0},
    ]


def daily_sales() -> List[dict]:
    """Le sell-out au jour, inventé : trois marchés, six semaines lues jusqu'à hier, et
    les mêmes dates un an plus tôt. Le Japon encaisse une campagne le 1er du mois."""
    import datetime

    today = datetime.date.today()
    rows = []
    bases = {("JAPAN", "JP"): 70_000.0, ("FRANCE", "FR"): 42_000.0, ("CHINA", "CN"): 95_000.0}
    for (market, iso2), base in bases.items():
        for back in range(1, 43):
            day = today - datetime.timedelta(days=back)
            weekend = 1.35 if day.weekday() >= 5 else 1.0
            amount = base * weekend * (1.0 + 0.02 * ((back * 7) % 5))
            if market == "JAPAN" and day.day == 1:
                amount += 900_000.0
            rows.append({"market": market, "iso2": iso2, "transaction_date": day.isoformat(),
                         "net_sales_eur": round(amount, 2)})
            before = day - datetime.timedelta(days=364)
            rows.append({"market": market, "iso2": iso2, "transaction_date": before.isoformat(),
                         "net_sales_eur": round(amount * 0.94, 2)})
    return rows


#: Des partenaires inventés, sous des codes inventés : le nom vient d'un fichier hors dépôt
#: chez le vrai lecteur, ici il est joué par le libellé. Deux e-retailers, un grand
#: magasin, un opérateur de voyage — dix-huit mois, pour que l'exercice à date ait son an
#: dernier en face.
PARTNER_SHAPES = {
    # code, libellé, canal, pays de facturation, base mensuelle, croissance annuelle
    "PC_WEB_A": ("ORBIS MARKET", "WEBP", "LU", 420_000.0, 0.14),
    "PC_WEB_B": ("NORDIC WEB", "WEBP", "SE", 160_000.0, -0.09),
    "PC_DPT_A": ("GRAND BAZAR", "DPT", "FR", 230_000.0, 0.02),
    "PC_TRA_A": ("SOLSTICE DUTY FREE", "TRA", "HK", 310_000.0, -0.21),
}


def partner_rows() -> List[dict]:
    """Le sell-in facturé par partenaire, au mois, inventé."""
    rows = []
    for code, (label, channel, iso2, base, yearly) in PARTNER_SHAPES.items():
        for back in range(17, -1, -1):
            index = 2026 * 12 + 7 - back
            period = "%04d-%02d" % (index // 12, index % 12 + 1)
            seasonal = 1.0 + 0.25 * ((index % 12) in (9, 10))
            value = base * seasonal * (1.0 + yearly) ** ((17 - back) / 12.0)
            rows.append({"period": period, "code": code, "label": label, "channel": channel,
                         "iso2": iso2, "net_eur": round(value, 2)})
    return rows


def _months_back(count: int = 17) -> List[str]:
    return ["%04d-%02d" % ((2026 * 12 + 7 - back) // 12, (2026 * 12 + 7 - back) % 12 + 1)
            for back in range(count, -1, -1)]


def osa_rows() -> List[dict]:
    """Le service en boutique inventé : quatre unités, une sous la cible."""
    rows = []
    shapes = {"Northland": 0.012, "Eastland": 0.018, "Westland": 0.009, "Southland": 0.11}
    for index, period in enumerate(_months_back()):
        for unit, out in shapes.items():
            demand = 900_000.0 + 40_000.0 * (index % 5)
            rupture = demand * (out + 0.002 * ((index + len(unit)) % 3))
            rows.append({"period": period, "unit": unit, "rupture_eur": round(rupture, 2),
                         "demand_eur": round(demand, 2), "lines": 5000 + 37 * index})
    return rows


def forecast_rows() -> List[dict]:
    """La prévision à M-3 contre le réel, inventée : un marché sous sa prévision, un au-dessus."""
    rows = []
    shapes = {"Northland": 0.08, "Eastland": -0.06, "Westland": 0.01, "Southland": 0.03}
    for index, period in enumerate(_months_back()):
        for market, bias in shapes.items():
            actual = 700_000.0 + 25_000.0 * (index % 4)
            rows.append({"period": period, "market": market,
                         "forecast_eur": round(actual * (1 + bias + 0.004 * (index % 3)), 2),
                         "actual_eur": round(actual, 2)})
    return rows


def order_rows() -> List[dict]:
    """Le sell-in livré sur commandé, inventé : un canal qui livre mal."""
    rows = []
    shapes = {"WEBP": 0.95, "DIS": 0.62, "TRA": 0.88, "WHOCH": 0.91}
    for index, period in enumerate(_months_back()):
        for channel, rate in shapes.items():
            ordered = 500_000.0 + 30_000.0 * (index % 6)
            delivered = ordered * (rate - 0.01 * (index % 2))
            rows.append({"period": period, "channel": channel, "ordered_eur": round(ordered, 2),
                         "delivered_eur": round(delivered, 2),
                         "complete_eur": round(delivered * 0.8, 2), "lines": 800 + 11 * index})
    return rows


#: Le vrac ligne à ligne, inventé : trois marchés, cinq points de vente, deux valeurs du
#: drapeau, quelques gammes — concentré comme il l'est, un compte qui monte, un qui s'arrête.
BULK_SHAPES = (
    # marché, drapeau, sous-canal, code point de vente, base mensuelle, croissance annuelle
    ("China", 2, "WHOLESALE", "ST-CN-0410", 260_000.0, 0.35),
    ("China", 3, "WHOLESALE", "ST-CN-0418", 90_000.0, -0.02),
    ("Hong Kong", 2, "TRAVEL RETAIL", "ST-HK-0021", 110_000.0, -0.40),
    ("Japan", 5, "CORPORATE", "ST-JP-0130", 22_000.0, 0.05),
    ("Brazil", 4, "WHOLESALE", "ST-BR-0007", 15_000.0, 0.12),
)
BULK_RANGES = ("Karité", "Amande", "Verveine", "Immortelle")


def bulk_rows() -> List[dict]:
    """Le vrac de l'entrepôt ligne à ligne, inventé."""
    rows = []
    for index, period in enumerate(_months_back()):
        for market, flag, sub_channel, store, base, yearly in BULK_SHAPES:
            monthly = base * (1.0 + yearly) ** (index / 12.0) * (1.0 + 0.15 * ((index + flag) % 3 == 0))
            for rank, range_name in enumerate(BULK_RANGES):
                share = (0.5, 0.25, 0.15, 0.10)[(rank + flag) % 4]
                rows.append({"period": period, "market": market, "flag": flag,
                             "sub_channel": sub_channel, "store": store,
                             "range_name": range_name,
                             "net_eur": round(monthly * share, 2), "lines": 3 + rank})
    return rows


def sell_in_daily() -> List[dict]:
    """Le sell-in facturé au jour, inventé : trois pays, deux canaux, les jours ouvrés depuis
    le 1er du mois jusqu'à hier, et le même mois un an plus tôt en entier."""
    import datetime

    today = datetime.date.today()
    first = today.replace(day=1)
    rows = []
    bases = {("JP", "webp"): 60_000.0, ("FR", "dis"): 35_000.0, ("CN", "tra"): 80_000.0}
    for window, start in ((INVOICED_CURRENT, first),
                          (INVOICED_LAST_YEAR, first.replace(year=first.year - 1))):
        day = start
        end = today - datetime.timedelta(days=1) if window == INVOICED_CURRENT else (
            (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1))
        while day <= end:
            if day.weekday() < 5:
                for (iso2, channel), base in bases.items():
                    factor = 0.9 if window == INVOICED_LAST_YEAR else 1.0
                    rows.append({"window": window, "invoice_date": day.isoformat(), "iso2": iso2,
                                 "channel": channel, "net_eur": round(base * factor, 2)})
            day += datetime.timedelta(days=1)
    return rows


INVOICED_CURRENT = "current"
INVOICED_LAST_YEAR = "last_year"


def month_targets(period: str) -> dict:
    return {"Japan": 4_000_000.0, "France": 2_400_000.0, "China": 6_500_000.0}



#: Les produits inventés : six catégories, neuf gammes, deux ou trois références par gamme.
#: Leur somme mensuelle est calée sur les ventes hors vrac de `kpi_rows`, pour que la
#: couverture — la lecture produit contre la lecture des KPI — se lise pleine en démo.
PRODUCT_SCALE = 3.55
#: Aucun nom réel ; les mots de catégorie sont ceux de n'importe quelle maison de beauté.
#: Une gamme est lancée sur l'exercice, une autre arrêtée l'hiver dernier.
PRODUCT_RANGES = (
    # gamme, catégorie, ventes mensuelles de base, croissance annuelle, références
    ("Sable d'Or", "Corps", 2_600_000.0, 0.09, ("crème mains", "lait corps", "savon")),
    ("Miel des Cimes", "Corps", 1_900_000.0, -0.06, ("crème mains", "gel douche", "baume")),
    ("Rosée de Roche", "Visage", 1_500_000.0, 0.14, ("sérum", "crème jour", "masque")),
    ("Aube Boréale", "Visage", 900_000.0, -0.11, ("crème nuit", "huile")),
    ("Lin Sauvage", "Cheveux", 1_100_000.0, 0.03, ("shampoing", "après-shampoing")),
    ("Brume de Cèdre", "Parfum", 1_300_000.0, 0.05, ("eau de toilette", "eau de parfum")),
    ("Écorce Noire", "Maison", 700_000.0, -0.02, ("bougie", "diffuseur")),
    ("Bois de Reine", "Coffrets", 400_000.0, 0.0, ("coffret mains", "coffret corps")),
    ("Pluie d'Argile", "Visage", 350_000.0, 0.0, ("gommage",)),
)
PRODUCT_LAUNCHED = "Bois de Reine"
PRODUCT_LAUNCHED_FROM = "2026-05"
PRODUCT_STOPPED = "Pluie d'Argile"
PRODUCT_STOPPED_AFTER = "2025-12"
PRODUCT_HEROES = ("Sable d'Or crème mains", "Rosée de Roche sérum")
#: Trois marchés portent les catégories et les gammes ; les références ne sont lues qu'au
#: niveau du groupe, comme dans l'entrepôt.
PRODUCT_MARKETS = {"Japan": (0.21, -0.05), "Brazil": (0.06, 0.08), "China": (0.26, 0.02),
                   "France": (0.12, 0.01)}


def product_rows() -> List[dict]:
    """Ce que la lecture produit rapporte de brut, inventé : dix-huit mois de sell-out par
    catégorie, gamme et référence pour le groupe, et par catégorie et gamme pour trois
    marchés — de quoi lire l'exercice à date contre l'an dernier, un lancement et un
    arrêt."""
    rows: List[dict] = []
    for back in range(17, -1, -1):
        index = 2026 * 12 + 7 - back
        period = "%04d-%02d" % (index // 12, index % 12 + 1)
        seasonal = 1.0 + 0.10 * ((index % 12) in (10, 11))
        by_category: Dict[str, float] = {}
        by_range: Dict[str, float] = {}
        for name, category, base, yearly, items in PRODUCT_RANGES:
            if name == PRODUCT_LAUNCHED and period < PRODUCT_LAUNCHED_FROM:
                continue
            if name == PRODUCT_STOPPED and period > PRODUCT_STOPPED_AFTER:
                continue
            total = PRODUCT_SCALE * base * seasonal * (1.0 + yearly) ** ((17 - back) / 12.0)
            weights = [1.0 / (position + 1) for position in range(len(items))]
            for position, item in enumerate(items):
                label = "%s %s" % (name, item)
                # La première référence de la gamme porte la tendance plus fort que les
                # autres : ce qui pousse pousse d'abord par son produit de tête.
                twist = 1.0 + (0.4 if position == 0 else -0.2) * yearly * ((17 - back) / 12.0)
                value = total * weights[position] / sum(weights) * twist
                rows.append({"scope": "LOEP", "level": "product", "name": label,
                             "period": period, "net_sales": round(value),
                             "is_hero": 1 if label in PRODUCT_HEROES else 0})
                by_range[name] = by_range.get(name, 0.0) + value
                by_category[category] = by_category.get(category, 0.0) + value
        for name, value in by_range.items():
            rows.append({"scope": "LOEP", "level": "range", "name": name, "period": period,
                         "net_sales": round(value)})
        for name, value in by_category.items():
            rows.append({"scope": "LOEP", "level": "category", "name": name,
                         "period": period, "net_sales": round(value)})
        for market, (weight, shift) in PRODUCT_MARKETS.items():
            factor = weight * (1.0 + shift) ** ((17 - back) / 12.0)
            for name, value in by_range.items():
                rows.append({"scope": market, "level": "range", "name": name,
                             "period": period, "net_sales": round(value * factor)})
            for name, value in by_category.items():
                rows.append({"scope": market, "level": "category", "name": name,
                             "period": period, "net_sales": round(value * factor)})
    return rows


def client_rows() -> List[dict]:
    """Voir plus bas : rempli avec le module clients."""
    return _client_rows()


def kpi_rows() -> List[dict]:
    """Ce que la lecture des KPI rapporte de brut, inventé : quinze mois de ventes à
    magasins comparables, pour le groupe et trois marchés, avec des valeurs qui donnent une
    croissance lisible sur le mois et sur l'exercice."""
    rows: List[dict] = []
    shapes = {
        "LOEP": (24_000_000.0, 0.021),
        "Japan": (5_100_000.0, -0.038),
        "Brazil": (1_400_000.0, 0.064),
        "China": (6_300_000.0, 0.012),
    }
    for scope, (base, yearly) in shapes.items():
        for back in range(17, -1, -1):
            index = 2026 * 12 + 7 - back
            period = "%04d-%02d" % (index // 12, index % 12 + 1)
            seasonal = 1.0 + 0.08 * ((index % 12) in (10, 11))
            value = base * seasonal * (1.0 + yearly) ** ((17 - back) / 12.0)
            rows.append({"scope": scope, "kpi_key": "same_store_sales", "period": period,
                         "value": round(value)})
            # Toutes les ventes, et les mêmes sans le vrac : un huitième de vrac en Chine,
            # presque rien ailleurs — de quoi lire les deux bases.
            bulk_share = {"China": 0.12, "LOEP": 0.035}.get(scope, 0.01)
            whole = value * 1.6
            rows.append({"scope": scope, "kpi_key": "net_sales", "period": period,
                         "value": round(whole)})
            rows.append({"scope": scope, "kpi_key": "net_sales_hors_bulk", "period": period,
                         "value": round(whole * (1 - bulk_share))})
    return rows


#: Les clients inventés : le pont et le flux, pour le groupe et trois marchés. La base de
#: l'an dernier s'érode chez les fidèles et le recrutement compense en nombre, pas en
#: valeur — la lecture que le bloc doit savoir dire.
CLIENT_SHAPES = {
    #            arc_ly, arc_ty, retained, reactivated, new, atv_ly, atv_ty_retained, atv_new, walkin_ly, walkin_ty
    "LOEP":  (1_900_000, 1_960_000, 1_150_000, 210_000, 600_000, 78.0, 80.0, 61.0, 2_400_000, 2_300_000),
    "Japan": (420_000, 400_000, 260_000, 40_000, 100_000, 64.0, 63.0, 52.0, 610_000, 570_000),
    "China": (380_000, 430_000, 220_000, 50_000, 160_000, 92.0, 96.0, 70.0, 300_000, 320_000),
    "France": (210_000, 214_000, 130_000, 24_000, 60_000, 58.0, 60.0, 47.0, 480_000, 470_000),
}
CLIENT_THROUGH = "2026-08"


def _client_rows() -> List[dict]:
    rows: List[dict] = []
    for scope, shape in CLIENT_SHAPES.items():
        (arc_ly, arc_ty, retained, reactivated, new, atv_ly, atv_ret, atv_new,
         walkin_ly, walkin_ty) = shape
        lost = arc_ly - retained
        tickets = 1.6
        def row(window, segment, clients, atv, per=tickets):
            transactions = clients * per
            rows.append({"scope": scope, "window": window, "through": CLIENT_THROUGH,
                         "segment": segment, "clients": clients,
                         "transactions": round(transactions), "sales": round(transactions * atv)})
        # L'exercice d'avant, pour que la part perdue de l'an dernier se lise : une base
        # un peu plus petite, un flux un peu moins érodé.
        row("ly2", "arc", round(arc_ly * 0.96), atv_ly * 0.97)
        row("ly2", "walkin", round(walkin_ly * 1.03), atv_ly * 0.68, per=1.0)
        row("ly", "retained", round(arc_ly * 0.96 * 0.64), atv_ly * 1.02, per=1.9)
        row("ly", "reactivated", round(arc_ly * 0.10), atv_ly * 0.94, per=1.3)
        row("ly", "lost", round(arc_ly * 0.96 * 0.36), atv_ly * 0.9, per=1.2)
        row("ly", "new", arc_ly - round(arc_ly * 0.96 * 0.64) - round(arc_ly * 0.10), atv_ly * 0.8, per=1.15)
        row("ly", "arc", arc_ly, atv_ly)
        row("ly", "walkin", walkin_ly, atv_ly * 0.7, per=1.0)
        row("ty", "retained", retained, atv_ret, per=1.9)
        row("ty", "reactivated", reactivated, atv_ly * 0.95, per=1.3)
        row("ty", "new", new, atv_new, per=1.15)
        for channel, part, atv_twist in (("MALL STORE", 0.62, 1.05), ("E-COMMERCE", 0.33, 0.9),
                                         ("MARKETPLACE", 0.05, 0.8)):
            rows.append({"scope": scope, "window": "ty", "through": CLIENT_THROUGH, "segment": "new",
                         "clients": round(new * part), "transactions": round(new * part * 1.15),
                         "sales": round(new * part * 1.15 * atv_new * atv_twist), "channel": channel})
            rows.append({"scope": scope, "window": "ly", "through": CLIENT_THROUGH, "segment": "new",
                         "clients": round(new * 0.9 * (part + (0.03 if channel == "MALL STORE" else -0.015))),
                         "transactions": round(new * 0.9 * part * 1.15),
                         "sales": round(new * 0.9 * part * 1.15 * atv_ly * 0.8), "channel": channel})
        row("ty", "lost", lost, atv_ly * 0.9, per=1.2)
        # Les perdus et la base par canal du dernier ticket, sur les deux exercices : la
        # boutique perd un peu plus que le site, et un peu plus que l'an dernier.
        for channel, part, base_part, rate_twist in (("MALL STORE", 0.80, 0.78, 1.02),
                                                     ("E-COMMERCE", 0.20, 0.22, 0.95)):
            for window, base_window, scale in (("ty", "ly", 1.0), ("ly", "ly2", 0.96)):
                base_clients = round(arc_ly * (0.96 if base_window == "ly2" else 1.0) * base_part)
                lost_clients = round(lost * scale * part * rate_twist)
                rows.append({"scope": scope, "window": base_window, "through": CLIENT_THROUGH,
                             "segment": "arc", "clients": base_clients,
                             "transactions": round(base_clients * 1.6),
                             "sales": round(base_clients * 1.6 * atv_ly), "channel": channel})
                rows.append({"scope": scope, "window": window, "through": CLIENT_THROUGH,
                             "segment": "lost", "clients": lost_clients,
                             "transactions": round(lost_clients * 1.2),
                             "sales": round(lost_clients * 1.2 * atv_ly * 0.9), "channel": channel})
        row("ty", "walkin", walkin_ty, atv_ly * 0.72, per=1.0)
        # Le pont de l'exercice : la somme des trois segments actifs.
        active = [r for r in rows if r["scope"] == scope and r["window"] == "ty"
                  and r["segment"] in ("retained", "reactivated", "new") and not r.get("channel")]
        rows.append({"scope": scope, "window": "ty", "through": CLIENT_THROUGH, "segment": "arc",
                     "clients": sum(r["clients"] for r in active),
                     "transactions": sum(r["transactions"] for r in active),
                     "sales": sum(r["sales"] for r in active)})
    return rows


#: Le sell-in inventé, par segment de plan et par mois : l'exercice à date avec l'an dernier
#: en face, et l'exercice clos. Un canal court devant son rythme, les autres non.
SELL_IN_SHAPES = {
    "TRA - Travel Retail": (2_400_000.0, 1.0, 1.7),
    "WEBP - Web Partners": (1_800_000.0, 1.0, 1.05),
    "DIS - Distributors": (1_200_000.0, 1.0, 0.95),
    "WHOCH - Wholesale Chains": (600_000.0, 1.0, 1.1),
}


def sell_in_series():
    current, closed = [], []
    for segment, (base, ly_twist, recent_twist) in SELL_IN_SHAPES.items():
        for back in range(11, -1, -1):
            index = 2026 * 12 + 2 - back           # avril 2025 à mars 2026
            period = "%04d-%02d" % (index // 12, index % 12 + 1)
            closed.append({"entity": "ENT_1", "segment": segment, "period": period,
                           "value": round(base * (1.15 if (index % 12) in (9, 10) else 1.0))})
        for month in range(4, 9):                  # avril à août 2026
            recent = recent_twist if month >= 6 else 1.0
            current.append({"entity": "ENT_1", "segment": segment, "period": "2026-%02d" % month,
                            "market": "Group", "sales_actual": round(base * recent),
                            "sales_last_year": round(base * ly_twist)})
    return current, closed

"""One hand-written slide per layout, shared by the placement, lint and export tests."""
from __future__ import annotations

from lectern.schema import (BulletsNode, ChartNode, Item, ItemsNode, Node, QuoteNode, Series, Slide, StatNode,
                            TableNode, TextNode)


def slide(index: int, layout: str, headline: str, nodes: list[Node], section: str | None = "The risk",
          notes: str = "Say why this matters to the board.") -> Slide:
    return Slide(id=f"s{index}", index=index, section=section, headline=headline, layout=layout,  # type: ignore[arg-type]
                 nodes=[TextNode(role="headline", value=headline), *nodes], notes=notes, status="ready")


PLAN = [
    Item(title="Find accounts at risk", body="Score every account on usage, support load and renewal date."),
    Item(title="Fix the first 90 days", body="Rebuild onboarding so new logos reach value sooner."),
    Item(title="Measure churn monthly", body="Report logo churn to the board every month."),
]


def all_layouts() -> list[Slide]:
    return [
        slide(1, "title", "Q3 board review", [
            TextNode(role="subhead", value="Revenue is up 34%, and churn needs a decision"),
            TextNode(role="caption", value="Board of directors · October 2026")], section=None),
        slide(2, "agenda", "What we will cover today", [ItemsNode(style="steps", items=[
            Item(title=t) for t in ["Where we stand", "What is working", "The churn risk", "The retention plan",
                                    "The decision we need"]])]),
        slide(3, "section", "The risk", [
            TextNode(role="subhead", value="Monthly logo churn has risen for two quarters")]),
        slide(4, "big_idea", "Growth is strong, but we are losing customers faster than we planned", [
            TextNode(role="body", value="Revenue is up 34% while monthly logo churn rose from 2.6% to 4.1%.")]),
        slide(5, "bullets", "Three things explain the quarter", [BulletsNode(items=[
            "Revenue is up 34% on last year", "Monthly logo churn rose from 2.6% to 4.1%",
            "A $1.2M retention budget brings churn back under control",
            "New logos are not reaching value in their first 90 days"])]),
        slide(6, "two_column", "Growth is working while retention is slipping", [ItemsNode(style="columns", items=[
            Item(title="What is working",
                 body="Revenue is up 34%\nNew logo pipeline is healthy\nExpansion is ahead of plan"),
            Item(title="What is not",
                 body="Monthly logo churn is 4.1%\nOnboarding takes too long\nNo owner for at-risk accounts")])]),
        slide(7, "three_column", "The retention plan has three parts", [ItemsNode(style="columns", items=PLAN)]),
        slide(8, "process", "We bring churn down in four steps", [ItemsNode(style="steps", items=[
            *PLAN, Item(title="Review with the board", body="Decide on the next tranche in Q1.")])]),
        slide(9, "timeline", "The plan pays back within three quarters", [ItemsNode(style="timeline", items=[
            Item(title="Budget approved", label="Oct 2026"),
            Item(title="Team hired", body="Four customer success managers start.", label="Dec 2026"),
            Item(title="Churn under 3%", label="Q2 2027"),
            Item(title="Churn back to 2.6%", label="Q3 2027")])]),
        slide(10, "chart", "Monthly logo churn rose from 2.6% to 4.1%", [
            ChartNode(kind="bar", categories=["Q2", "Q3"],
                      series=[Series(name="Monthly logo churn", values=[2.6, 4.1])], unit="%"),
            TextNode(role="body", value="Churn has risen 1.5 points in one quarter. At this rate we lose four "
                                        "in ten logos a year."),
            TextNode(role="caption", value="Source: billing data, Q3")]),
        slide(11, "dashboard", "The quarter comes down to three numbers", [
            StatNode(value="34%", caption="Revenue growth, year on year"),
            StatNode(value="4.1%", caption="Monthly logo churn, up from 2.6%"),
            StatNode(value="$1.2M", caption="Retention budget requested")]),
        slide(12, "table", "Option B gives the best return for the budget", [TableNode(
            columns=["Option", "Cost", "Churn impact", "Time to effect"],
            rows=[["A. Do nothing", "$0", "None", "—"], ["B. Retention team", "$1.2M", "−1.5 points", "2 quarters"],
                  ["C. Pricing change", "$0.4M", "−0.5 points", "3 quarters"]])]),
        slide(13, "quote", "What customers tell us", [QuoteNode(
            text="We bought it for the reporting, and nobody showed us how to set it up.",
            attribution="Head of Operations, mid-market customer")]),
        slide(14, "case_study", "One account shows what the plan fixes", [
            ItemsNode(style="columns", items=[
                Item(title="Challenge", body="Usage fell in month two."),
                Item(title="Solution", body="A named success manager rebuilt onboarding."),
                Item(title="Results", body="Renewed and expanded within the year.")]),
            StatNode(value="2x", caption="Seats after renewal"),
            QuoteNode(text="It finally works the way we were sold.", attribution="VP Finance")]),
        slide(15, "diagram", "Churn signals flow into one health score", [ItemsNode(style="steps", items=[
            Item(title="Product usage", body="Weekly active seats"),
            Item(title="Support", body="Tickets and time to resolve"),
            Item(title="Health score", body="One number per account"),
            Item(title="Success team", body="Acts on accounts below 60")])]),
        slide(16, "team", "The retention team reports to the COO", [ItemsNode(style="columns", items=[
            Item(title="Maya Chen", label="VP Customer Success", body="Built the success team at two SaaS companies."),
            Item(title="Luis Ortega", label="Head of Onboarding"),
            Item(title="Priya Nair", label="Data lead", body="Owns the health score.")])]),
        slide(17, "summary", "Approve the budget and churn returns to 2.6%", [BulletsNode(items=[
            "Revenue is up 34%", "Monthly logo churn rose from 2.6% to 4.1%",
            "A $1.2M retention budget fixes the first 90 days"])]),
        slide(18, "next_steps", "We need three decisions from the board today", [ItemsNode(style="steps", items=[
            Item(title="Approve the $1.2M retention budget", label="Board · Today"),
            Item(title="Hire four success managers", body="Start interviews next week.", label="COO · 30 days"),
            Item(title="Report churn monthly", label="CFO · From November")])]),
        slide(19, "closing", "Thank you", [
            TextNode(role="subhead", value="Questions and discussion"),
            TextNode(role="caption", value="maya@example.com")], section=None),
        slide(20, "appendix", "Churn by segment", [TableNode(
            columns=["Segment", "Q2", "Q3"],
            rows=[["SMB", "3.4%", "5.6%"], ["Mid-market", "2.1%", "3.2%"], ["Enterprise", "0.8%", "0.9%"]])],
            section="Appendix"),
        slide(21, "big_number", "Revenue grew 34% this quarter", [
            StatNode(value="34%", caption="Revenue growth, year on year", source="Source: Q3 management accounts"),
            BulletsNode(items=["New logos drove most of the growth", "Expansion revenue is ahead of plan",
                               "Pricing held through the quarter"])]),
    ]


LONG = ("This is a deliberately long piece of text that keeps going well past what any reasonable slide would "
        "carry, so that the placement engine has to step the font size down and the lint has something to find")


def stress_layouts() -> list[Slide]:
    """The same layouts with too much content: nothing may leave the canvas or drop under the minimum size."""
    out = []
    for base in all_layouts():
        nodes: list[Node] = []
        for node in base.nodes:
            if isinstance(node, TextNode):
                nodes.append(TextNode(role=node.role, value=f"{node.value} {LONG}"))
            elif isinstance(node, BulletsNode):
                nodes.append(BulletsNode(items=[f"{i} {LONG}" for i in node.items] * 2))
            elif isinstance(node, ItemsNode):
                nodes.append(ItemsNode(style=node.style, items=[
                    Item(title=f"{i.title} {LONG[:60]}", body=LONG, label=i.label) for i in node.items] * 2))
            elif isinstance(node, StatNode):
                nodes.append(StatNode(value="$1,234,567,890", caption=LONG, source=LONG[:80]))
            elif isinstance(node, QuoteNode):
                nodes.append(QuoteNode(text=f"{node.text} {LONG} {LONG}", attribution=LONG[:90]))
            elif isinstance(node, TableNode):
                nodes.append(TableNode(columns=node.columns, rows=[[LONG[:70]] * len(node.columns)] * 9))
            else:
                nodes.append(node)
        nodes.append(BulletsNode(items=["An extra list the layout has no slot for", "It must still be placed"]))
        out.append(base.model_copy(update={"headline": f"{base.headline} {LONG}", "nodes": nodes}))
    return out

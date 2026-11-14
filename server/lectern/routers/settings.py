"""Connections (provider keys, stored locally and never returned), model routing, and the user's rules."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from pydantic import ValidationError
from sqlmodel import select

from .. import store
from ..db import session
from ..llm import router as llm
from ..models import FindingRow, RuleRow
from ..schema import (Connection, ConnectionTest, ConnectionUpdate, Routing, RoutingUpdate, Rule, RuleCreate)

router = APIRouter(tags=["settings"])


# ---------------------------------------------------------------- connections
@router.get("/settings/connections", response_model=list[Connection])
async def get_connections() -> list[Connection]:
    return llm.list_connections()


@router.put("/settings/connections", response_model=list[Connection])
async def put_connections(body: Any = Body(...)) -> list[Connection]:
    """Set a key and/or base URL. Accepts one `{id, api_key?, base_url?}`, a list of them, or
    `{connections: [...]}`. An empty string clears a value. Keys are never returned."""
    if isinstance(body, dict) and isinstance(body.get("connections"), list):
        items = body["connections"]
    elif isinstance(body, list):
        items = body
    else:
        items = [body]
    try:
        updates = [ConnectionUpdate.model_validate(item) for item in items]
    except ValidationError as error:
        raise store.Conflict("Each connection needs an id, and optionally api_key and base_url.") from error
    for update in updates:
        key = update.api_key if update.api_key is not None else update.key
        if not llm.update_connection(update.id, key, update.base_url):
            raise store.NotFound(f"There is no connection called \"{update.id}\".")
    return llm.list_connections()


@router.post("/settings/connections/{connection_id}/test", response_model=ConnectionTest,
             response_model_exclude_none=True)
async def test_connection(connection_id: str) -> ConnectionTest:
    outcome = await llm.test_connection(connection_id)
    if outcome is None:
        raise store.NotFound(f"There is no connection called \"{connection_id}\".")
    ok, detail, models = outcome
    return ConnectionTest(ok=ok, detail=detail, models=models)


# ---------------------------------------------------------------- routing
@router.get("/settings/routing", response_model=Routing)
async def get_routing() -> Routing:
    return llm.get_routing()


@router.put("/settings/routing", response_model=Routing)
async def put_routing(body: RoutingUpdate) -> Routing:
    try:
        return llm.set_routing(body.preset, body.roles)
    except ValueError as error:
        raise store.Conflict(str(error)) from error


# ---------------------------------------------------------------- rules
def _to_rule(row: RuleRow) -> Rule:
    return Rule(id=row.id, text=row.text, created_at=row.created_at, source=row.source)


@router.get("/rules", response_model=list[Rule])
async def list_rules() -> list[Rule]:
    with session() as s:
        return [_to_rule(r) for r in s.exec(select(RuleRow).order_by(RuleRow.created_at)).all()]


@router.post("/rules", response_model=Rule)
async def create_rule(body: RuleCreate) -> Rule:
    row = RuleRow(text=body.text.strip(), source=body.source or "user")
    with session() as s:
        s.add(row)
        s.commit()
    return _to_rule(row)


def _delete_rule(rule_id: str) -> dict[str, bool]:
    with session() as s:
        row = s.get(RuleRow, rule_id)
        if row is None:
            raise store.NotFound("That rule does not exist.")
        for finding in s.exec(select(FindingRow).where(FindingRow.rule_id == rule_id)).all():
            finding.rule_id = None
            s.add(finding)
        s.delete(row)
        s.commit()
    return {"ok": True}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str) -> dict[str, bool]:
    return _delete_rule(rule_id)


@router.delete("/rules")
async def delete_rule_by_query(id: str) -> dict[str, bool]:
    return _delete_rule(id)

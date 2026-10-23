from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg import Connection

from app.db import get_connection
from app.security import authorize_customer

router = APIRouter(
    prefix="/api/v1/customers", tags=["customers"],
    dependencies=[Depends(authorize_customer)],
)
Database = Annotated[Connection, Depends(get_connection)]
CustomerId = Annotated[int, Path(gt=0)]


def json_response(value):
    return JSONResponse(jsonable_encoder(value, custom_encoder={Decimal: str}))


def require_customer(value):
    if value is None:
        raise HTTPException(404, "Zákazník neexistuje.")
    return value


def load_meters(conn, customer_id):
    row = conn.execute(
        "SELECT energy_app.get_customer_meters(%s) AS data", (customer_id,)
    ).fetchone()
    return require_customer(row["data"])


@router.get("/{customer_id}")
def customer(customer_id: CustomerId, conn: Database):
    row = conn.execute(
        """SELECT customer_id, customer_number, first_name, last_name
           FROM energy_registry_20261023.customers WHERE customer_id = %s""",
        (customer_id,),
    ).fetchone()
    return json_response(require_customer(row))


@router.get("/{customer_id}/connections")
def connections(customer_id: CustomerId, conn: Database):
    row = conn.execute(
        "SELECT energy_app.get_customer_connections(%s) AS data", (customer_id,)
    ).fetchone()
    return json_response(require_customer(row["data"]))


@router.get("/{customer_id}/meters")
def meters(customer_id: CustomerId, conn: Database):
    return json_response(load_meters(conn, customer_id))


@router.get("/{customer_id}/meters/{meter_id}/measurements")
def measurements(
    customer_id: CustomerId,
    meter_id: Annotated[int, Path(gt=0)],
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
    conn: Database,
    limit: Annotated[int, Query(ge=1, le=10000)] = 10000,
):
    # DB timestamps have no confirmed timezone: do not silently convert them.
    if start.tzinfo is not None or end.tzinfo is not None:
        raise HTTPException(422, "Použite lokálny dátum a čas bez Z alebo časového posunu; pásmo dát nie je potvrdené.")
    if not start < end or end - start > timedelta(days=31):
        raise HTTPException(422, "Interval musí byť rastúci a najviac 31 dní.")
    catalog = load_meters(conn, customer_id)
    allowed = any(
        meter.get("measurement_meter_id") == meter_id
        for connection in catalog.get("connections", [])
        for meter in connection.get("meters", [])
    )
    if not allowed:
        raise HTTPException(404, "Meradlo nie je priradené zákazníkovi.")
    rows = conn.execute(
        """SELECT meter_id, observed_at, energy_kwh, source_file_id
           FROM energy.measurements
           WHERE meter_id = %s AND observed_at >= %s AND observed_at < %s
           ORDER BY observed_at, source_file_id, energy_kwh
           LIMIT %s""",
        (meter_id, start, end, limit + 1),
    ).fetchall()
    return json_response({
        "customer_id": customer_id, "measurement_meter_id": meter_id,
        "from": start, "to": end, "unit": "kWh",
        "timezone": "unconfirmed", "duplicates_retained": True,
        "ownership_basis": "registry_snapshot",
        "items": rows[:limit], "truncated": len(rows) > limit,
    })

"""Deterministic demo profiles and explainable, pairwise matching estimates."""

from math import sin, pi

from fastapi import APIRouter, Depends, HTTPException

from app.security import authorize_customer

router = APIRouter(
    prefix="/api/v1/customers/{customer_id}/demo",
    tags=["demo matching"], dependencies=[Depends(authorize_customer)],
)


def bell(start, end, total):
    weights = [sin(pi * (i - start + .5) / (end - start)) if start <= i < end else 0 for i in range(96)]
    return [total * value / sum(weights) for value in weights]


def scenarios():
    return [
        {"id": "solar-home", "name": "Dom s fotovoltikou", "role": "producer", "has_ims": True,
         "price_eur_kwh": .09, "profile_kwh": bell(32, 68, 18), "confidence": .92},
        {"id": "day-home", "name": "Domácnosť s dennou spotrebou", "role": "consumer", "has_ims": True,
         "max_price_eur_kwh": .12, "profile_kwh": bell(28, 76, 14), "confidence": .92},
        {"id": "evening-home", "name": "Domácnosť s večernou spotrebou", "role": "consumer", "has_ims": True,
         "max_price_eur_kwh": .12, "profile_kwh": bell(68, 92, 14), "confidence": .92},
        {"id": "tdo-home", "name": "Domácnosť bez IMS – odhad", "role": "consumer", "has_ims": False,
         "max_price_eur_kwh": .11, "profile_kwh": [.1] * 96, "confidence": .55},
        {"id": "low-budget", "name": "Odberateľ s nízkym cenovým limitom", "role": "consumer", "has_ims": True,
         "max_price_eur_kwh": .07, "profile_kwh": bell(28, 76, 14), "confidence": .92},
    ]


def match(producer, consumer, reference_price=.20):
    """Each candidate is evaluated independently; no energy crosses time slots."""
    supply, demand = producer["profile_kwh"], consumer["profile_kwh"]
    price = producer["price_eur_kwh"]
    compatible = price <= consumer["max_price_eur_kwh"]
    intervals = [min(s, d) if compatible else 0 for s, d in zip(supply, demand)]
    volume = sum(intervals)
    total_supply, total_demand = sum(supply), sum(demand)
    overlap = volume / min(total_supply, total_demand) if min(total_supply, total_demand) > 0 else 0
    price_score = min(1, .6 + .4 * min(1, max(0, (reference_price - price) / reference_price) / .5)) if compatible else 0
    reliability = min(producer["confidence"], consumer["confidence"])
    balance = 1 - abs(total_supply - total_demand) / max(total_supply, total_demand) if max(total_supply, total_demand) else 0
    score = 100 * (.5 * overlap + .25 * price_score + .15 * reliability + .1 * balance) if volume > 0 else 0
    return {
        "producer_id": producer["id"], "consumer_id": consumer["id"],
        "eligible": compatible and volume > 0,
        "reason": "price_limit" if not compatible else "no_time_overlap" if not volume else "compatible",
        "score": round(score, 2),
        "components": {"overlap": overlap, "price": price_score, "reliability": reliability, "balance": balance},
        "shared_kwh": round(volume, 6), "interval_shared_kwh": intervals,
        "price_eur_kwh": price, "payment_eur": round(volume * price, 4),
        "estimated_consumer_saving_eur": round(volume * max(0, reference_price - price), 4),
        "estimated_producer_gain_eur": round(volume * (price - .04), 4),
    }


def metadata(customer_id):
    return {"customer_id": customer_id, "data_source": "synthetic_demo", "interval_minutes": 15,
            "date": "2025-06-15", "timezone": "Europe/Bratislava", "unit": "kWh",
            "reference_price_eur_kwh": .20, "feed_in_price_eur_kwh": .04,
            "fees_included": False, "network_charges_included": False}


@router.get("/scenarios")
def demo_scenarios(customer_id: int):
    return {**metadata(customer_id), "items": scenarios()}


@router.get("/matches")
def demo_matches(customer_id: int, scenario_id: str = "solar-home"):
    items = scenarios()
    selected = next((item for item in items if item["id"] == scenario_id), None)
    if selected is None:
        raise HTTPException(404, "Demo scenár neexistuje.")
    matches = [match(selected, item) if selected["role"] == "producer" else match(item, selected)
               for item in items if item["role"] != selected["role"]]
    matches.sort(key=lambda item: (-item["score"], item["producer_id"], item["consumer_id"]))
    return {**metadata(customer_id), "scenario_id": scenario_id,
            "allocation_mode": "independent_pair_estimates",
            "score_weights": {"overlap": .5, "price": .25, "reliability": .15, "balance": .1},
            "items": matches}

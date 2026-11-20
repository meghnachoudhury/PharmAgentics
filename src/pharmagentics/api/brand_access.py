"""Account brand grants, independent of persona roles and classification (core-010).

Grants come only from validated sign-in claims. Old sessions without grants fail closed.
Saved-record checks always use the persisted brand, never a query-string override.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

from pharmagentics.tools.brands import BRIEFING_ENGINES, PRODUCTS, briefing_brand

if TYPE_CHECKING:
    from .rbac import Principal, Role
    from .schemas import ReleaseContext

GRANTS = {"brand-bxa": "BXA", "brand-bxc": "BXC"}


def allowed_brands(p: Principal) -> set[str]:
    return {GRANTS[g] for g in p.brand_grants if g in GRANTS}


def require_brand(p: Principal, brand_id: str) -> None:
    if brand_id not in allowed_brands(p):
        raise HTTPException(status_code=403, detail="Your account has no access to this brand.")


def require_engine(brand_id: str, engine: str) -> None:
    try:
        briefing_brand(brand_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if engine not in BRIEFING_ENGINES[brand_id]:
        raise HTTPException(status_code=400, detail=f"{brand_id} does not support the {engine} Briefing engine.")


def context(release: ReleaseContext, p: Principal) -> ReleaseContext:
    from .schemas import ReleaseContext

    ids = sorted(set(release.product_ids) & set(BRIEFING_ENGINES) & allowed_brands(p))
    return ReleaseContext.model_validate({**release.model_dump(),
        "brand_id": ids[0] if ids else None,
        "product_ids": ids,
        "brands": [{"id": b, "name": PRODUCTS[b], "engines": list(BRIEFING_ENGINES[b])} for b in ids],
    })


def brief_for(p: Principal, role: Role, brief_id: str) -> dict:
    from . import store

    record = store.get_brief(brief_id)
    if (record is None or record["result"].get("brand_id", "BXA") not in allowed_brands(p)
            or ("review" not in role.actions and record["review_status"] != "approved")):
        raise HTTPException(status_code=404, detail="No such briefing.")
    return record


def job_for(p: Principal, job_id: str) -> dict:
    from . import jobs, rbac

    job = jobs.get(job_id)
    brand = ((job or {}).get("payload", {}).get("query") or {}).get("brand_id", "BXA")
    if job is None or job["by"] != rbac.pseudonym(p.sub) or brand not in allowed_brands(p):
        raise HTTPException(status_code=404, detail="No such job.")
    return job

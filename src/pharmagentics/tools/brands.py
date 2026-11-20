"""Server-owned product catalog and implemented Briefing engines (core-010).

Product IDs are validated before interpolation into the existing SQL builders.
Release membership and per-user grants are applied separately by the API.
"""

PRODUCTS = {"BXA": "Cardiovela", "BXC": "Lipidara", "BXD": "Vascriva", "BXE": "Metacora"}
BRIEFING_ENGINES = {"BXA": ("scripted", "agent"), "BXC": ("scripted",)}


def product_id(value: str) -> str:
    if value not in PRODUCTS:
        raise ValueError("Unknown product.")
    return value


def briefing_brand(value: str) -> str:
    if value not in BRIEFING_ENGINES:
        raise ValueError("This brand has no implemented Briefing workflow.")
    return product_id(value)

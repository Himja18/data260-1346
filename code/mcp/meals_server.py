"""DATA-260 HW5 Part 2A - "meals" MCP server over TheMealDB (s1346).

Four tools over the public TheMealDB API (test key "1"):
  search_meals_by_name(query, limit=5)    -> {results: [{id, name, area, category, thumb}], count, message}
  meals_by_ingredient(ingredient, limit=12) -> {results: [{id, name, thumb}], count, message}
  meal_details(id)                         -> {id, name, category, area, instructions, image,
                                               source, youtube, ingredients: [{name, measure}]}
  random_meal()                            -> same shape as meal_details

"meals": null from the API  -> empty result + short message (not an error).
Network / HTTP / JSON errors -> ToolError, which MCP Inspector shows as an error.

Run with the Inspector:   mcp dev code/mcp/meals_server.py
STDIO rule: never print to stdout (it carries the JSON-RPC stream); log to stderr only.
"""
import logging
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

logging.basicConfig(
    stream=sys.stderr,                       # stderr only - stdout is the JSON-RPC channel
    level=logging.INFO,
    format="%(asctime)s %(levelname)s meals: %(message)s",
)
log = logging.getLogger("meals")

API_BASE = "https://www.themealdb.com/api/json/v1/1"
TIMEOUT_S = 10.0

mcp = FastMCP("meals")

# All four tools only read from TheMealDB.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=True)


# ---- helpers --------------------------------------------------------------
def _get(endpoint: str, params: dict[str, Any] | None = None) -> dict:
    """GET one TheMealDB endpoint; turn transport/JSON problems into clean ToolErrors."""
    url = f"{API_BASE}/{endpoint}"
    log.info("GET %s params=%s", endpoint, params)
    try:
        resp = httpx.get(url, params=params, timeout=TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        raise ToolError(f"TheMealDB timed out after {TIMEOUT_S:.0f}s ({endpoint})")
    except httpx.HTTPStatusError as e:
        raise ToolError(f"TheMealDB returned HTTP {e.response.status_code} for {endpoint}")
    except httpx.HTTPError as e:
        raise ToolError(f"Network error calling TheMealDB ({endpoint}): {e.__class__.__name__}")
    except ValueError:
        raise ToolError(f"TheMealDB returned invalid JSON for {endpoint}")
    if not isinstance(data, dict) or "meals" not in data:
        raise ToolError(f"Unexpected response shape from {endpoint}")
    return data


def _check_limit(limit: int, hi: int = 25) -> int:
    if not isinstance(limit, int) or not 1 <= limit <= hi:
        raise ToolError(f"limit must be an integer between 1 and {hi}, got {limit!r}")
    return limit


def _require_text(value: str, field: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ToolError(f"{field} must be a non-empty string")
    return value


def _ingredients(meal: dict) -> list[dict]:
    """TheMealDB stores ingredients as strIngredient1..20 / strMeasure1..20."""
    out = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        if name:
            out.append({"name": name, "measure": (meal.get(f"strMeasure{i}") or "").strip()})
    return out


def _details(meal: dict) -> dict:
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource") or None,
        "youtube": meal.get("strYoutube") or None,
        "ingredients": _ingredients(meal),
    }


def _list_result(items: list[dict], what: str) -> dict:
    return {
        "results": items,
        "count": len(items),
        "message": None if items else f"no matches for {what}",
    }


# ---- tools ------------------------------------------------------------------
@mcp.tool(annotations=READ_ONLY)
def search_meals_by_name(query: str, limit: int = 5) -> dict:
    """Search meals by name (e.g. "Arrabiata"). Returns up to `limit` (1-25) meals with
    id, name, area (cuisine), category and thumbnail. Use the id with meal_details."""
    query = _require_text(query, "query")
    _check_limit(limit)
    meals = _get("search.php", {"s": query})["meals"] or []
    items = [{"id": m.get("idMeal"), "name": m.get("strMeal"), "area": m.get("strArea"),
              "category": m.get("strCategory"), "thumb": m.get("strMealThumb")}
             for m in meals[:limit]]
    log.info("search_meals_by_name(%r) -> %d", query, len(items))
    return _list_result(items, f"name '{query}'")


@mcp.tool(annotations=READ_ONLY)
def meals_by_ingredient(ingredient: str, limit: int = 12) -> dict:
    """List meals whose main ingredient matches (e.g. "chicken"). Returns small cards:
    id, name, thumbnail. limit 1-25."""
    ingredient = _require_text(ingredient, "ingredient")
    _check_limit(limit)
    meals = _get("filter.php", {"i": ingredient})["meals"] or []
    items = [{"id": m.get("idMeal"), "name": m.get("strMeal"), "thumb": m.get("strMealThumb")}
             for m in meals[:limit]]
    log.info("meals_by_ingredient(%r) -> %d", ingredient, len(items))
    return _list_result(items, f"ingredient '{ingredient}'")


@mcp.tool(annotations=READ_ONLY)
def meal_details(id: str | int) -> dict:
    """Full recipe for one meal id: category, area, instructions, image, source,
    youtube, and ingredients as [{name, measure}]."""
    meal_id = str(id).strip()
    if not meal_id.isdigit():
        raise ToolError(f"id must be a numeric meal id (e.g. 52771), got {id!r}")
    meals = _get("lookup.php", {"i": meal_id})["meals"]
    if not meals:
        log.info("meal_details(%s) -> no match", meal_id)
        return {"id": meal_id, "found": False, "message": f"no meal with id {meal_id}"}
    return _details(meals[0])


@mcp.tool(annotations=READ_ONLY)
def random_meal() -> dict:
    """One random meal, same shape as meal_details."""
    meals = _get("random.php")["meals"]
    if not meals:
        return {"found": False, "message": "no matches"}
    meal = _details(meals[0])
    log.info("random_meal -> %s %s", meal["id"], meal["name"])
    return meal


if __name__ == "__main__":
    mcp.run()          # STDIO transport by default

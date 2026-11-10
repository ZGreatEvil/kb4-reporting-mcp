import asyncio
import sys

import httpx

from config.settings import PRODUCTS, SettingsError, load_config
from knowbe4.client import PRODUCT_NAMES, KnowBe4APIError, KnowBe4Client, readable_error

# the smallest read-only query each product key can answer
PRODUCT_CHECKS = {
    "ksat": "query { account { benchmarkCompanySize } }",
    "phisher": 'query { phisherMessages(query: "", per: 1) { pagination { totalCount } } }',
    "piq": "query { passwordIqSchedule { isDefault } }",
    "coach": "query { securityCoachSetupStatus { vendorIntegrated } }",
}


async def check_products(c: KnowBe4Client, console: str) -> int:
    """one line per configured product key; a missing one is simply not listed"""
    failed = 0
    for product in PRODUCTS:
        if not c.has_product(console, product):
            continue
        try:
            if product == "events":
                await c.list_user_events(console, {"per_page": 1})
            else:
                await c.graph(console, product, PRODUCT_CHECKS[product])
            print({"console": console, "product": PRODUCT_NAMES[product], "status": "ok"})
        except (KnowBe4APIError, httpx.HTTPError, ValueError) as exc:
            failed += 1
            print({"console": console, "product": PRODUCT_NAMES[product], "status": "error", "reason": readable_error(exc)})
    return failed


async def main() -> int:
    cfg = load_config()
    c = KnowBe4Client(cfg)
    failed = 0
    try:
        for console, cc in cfg.consoles.items():
            if not cc.has_api_key:
                print({"console": console, "status": "skipped", "reason": f"{cc.api_key_env} not set"})
                continue
            # one line per console, and a bad key never stops the check of the others
            try:
                print(await c.health_check(console))
            except (KnowBe4APIError, httpx.HTTPError) as exc:
                failed += 1
                print({"console": console, "status": "error", "reason": readable_error(exc)})
            failed += await check_products(c, console)
    finally:
        await c.aclose()
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except (SettingsError, FileNotFoundError) as exc:
        sys.exit(str(exc))

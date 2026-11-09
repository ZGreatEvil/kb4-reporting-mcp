import asyncio
import sys

import httpx

from config.settings import SettingsError, load_config
from knowbe4.client import KnowBe4APIError, KnowBe4Client, readable_error


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
    finally:
        await c.aclose()
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except (SettingsError, FileNotFoundError) as exc:
        sys.exit(str(exc))

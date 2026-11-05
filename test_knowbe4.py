import asyncio
from config.settings import load_config
from knowbe4.client import KnowBe4Client

async def main():
    cfg=load_config()
    c=KnowBe4Client(cfg)
    try:
        for console, cc in cfg.consoles.items():
            if not cc.has_api_key:
                print({"console": console, "status": "skipped", "reason": f"{cc.api_key_env} not set"})
                continue
            print(await c.health_check(console))
    finally:
        await c.aclose()

if __name__=="__main__": asyncio.run(main())

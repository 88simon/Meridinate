"""Test the refresh market caps endpoint directly"""
import asyncio
import sys
sys.path.insert(0, 'src')

from meridinate.routers.tokens import refresh_market_caps
from meridinate.utils.models import RefreshMarketCapsRequest

async def test():
    try:
        request = RefreshMarketCapsRequest(token_ids=[96])
        result = await refresh_market_caps(request)
        print("SUCCESS:", result)
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())

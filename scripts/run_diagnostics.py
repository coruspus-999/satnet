import asyncio
from satnet.ingestion.fetcher import TLEFetcher
from satnet.ingestion.service import TLEIngestionService

async def go():
    svc = TLEIngestionService(fetcher=TLEFetcher(timeout_seconds=90.0))
    records, report = await svc.fetch_and_parse_with_report(
        "https://celestrak.org/NORAD/elements/gp.php",
        {"GROUP": "stations", "FORMAT": "tle"},
        desired_count=30,
    )
    print("records type:", type(records), "len:", len(records))
    print("report:", report)
    print("first record:", records[0] if records else None)

asyncio.run(go())

"""Company news and events from VCI, and RSS items, fetched, cleaned and snapshotted into
`backend/data/company_feed_log.db` (`company-feed`). Run by hand through
`backend/scripts/snapshot_company_feed.py`; nothing else calls it. `fetch.py` is the only
module that imports `vnstock`."""

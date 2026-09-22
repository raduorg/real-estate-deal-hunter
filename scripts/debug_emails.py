#!/usr/bin/env python3
"""Debug: dump raw email bodies from the inbox to files for analysis."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.email_listener.listener import EmailListener
from src.email_listener.parsers import extract_listing_urls


async def main() -> None:
    config = load_config()
    listener = EmailListener(config.email, None)
    listener.connect()
    try:
        msg_ids = listener._search_unread()[-6:]
        print(f"Fetching last {len(msg_ids)} unread emails:", msg_ids)
        dump_dir = Path("data/email_dumps")
        dump_dir.mkdir(parents=True, exist_ok=True)

        all_urls = set()
        for i, msg_id in enumerate(msg_ids):
            msg = listener._fetch_email(msg_id)
            if not msg:
                continue
            subject = listener._decode_header(msg.get("Subject", ""))
            html = listener._extract_body(msg)
            print(f"\n{'='*70}")
            print(f"[{i}] Subject: {subject[:80]}")
            print(f"    Body length: {len(html)} bytes")
            urls = extract_listing_urls(html)
            print(f"    URLs found here: {len(urls)}")
            for u in urls:
                all_urls.add(u)
            if not urls:
                fname = dump_dir / f"email_{i:02d}_none.html"
                fname.write_text(html)
                print(f"    Dumped body -> {fname}")
                # print a hint about links present in the doc
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "lxml")
                hrefs = [a.get("href") for a in soup.find_all("a", href=True)]
                print(f"    Total <a> tags: {len(hrefs)}")
                for h in hrefs[:8]:
                    print(f"      href: {h[:100]}")

        print(f"\n\nAll URLs across emails ({len(all_urls)}):")
        for u in sorted(all_urls):
            print("  ", u)
    finally:
        listener.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
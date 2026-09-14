# Real Estate AI Agent - Implementation Plan

## Pipeline Architecture

The system is a single vertical pipeline for each listing. Every layer is a
deterministic Python function operating on a shared state object. LLMs are used
only where unstructured perception is strictly needed (zone fallback + vision).

| # | Pipeline Layer | Implementation | Why |
|---|----------------|----------------|-----|
| 1 | Email Ingestion | Pure Code (IMAP) | Parsing headers + regexing links must be 100% reliable and instantaneous |
| 2 | Extraction (HTML/API) | Pure Code (BeautifulSoup / Regex) | Prices, surface area, lat/long from `<script>` tags are zero-cost |
| 3 | Zone Verification | Code First, LLM Fallback | Shapely point-in-polygon vs GeoJSON ($0, ~10ms); gpt-4o-mini fallback for street names |
| 4 | Early-Exit Filter | Pure Code (Math) | Asking price/sqm >30% above zone ceiling → drop immediately, no vision spend |
| 5 | Vision Evaluation | Structured Multimodal Call | Single inference pass (gemini-1.5-flash / gpt-4o-mini) with rigid JSON schema |
| 6 | Valuation & ROI | Pure Code (Formula) | Financial math in Python; LLMs make arithmetic errors |
| 7 | Telegram / WhatsApp Alert | Pure Code (HTTP POST) | Simple webhook to dispatch the alert |

## Orchestration: LangGraph

LangGraph wires the layers into a graph with **conditional branching** so cheap
code filters run before any paid vision call:

```
Ingest -> Extract -> Verify Zone -> Financial Sanity Check (Early Exit)
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
           [Passes sanity check]                  [Overpriced dump]
                    │                                       │
                    ▼                                       ▼
            Vision Evaluation                           END (Skip)
                    │
                    ▼
            Final Deal Alert
```

Rules:
- A **node is a plain Python function** over `ListingState` — no autonomous LLM personas.
- **LLM is invoked only in 2 nodes**: zone fallback (street extraction) and vision.
- The early-exit edge is a pure math predicate; it prevents any last-dollar spend.

### ListingState

```python
from typing import TypedDict, List, Optional

class ListingState(TypedDict):
    # Raw inputs
    url: str
    raw_title: str
    raw_description: str
    price_eur: float
    surface_sqm: float
    image_urls: List[str]

    # Extraction & Spatial Data
    raw_coordinates: Optional[tuple[float, float]]
    canonical_zone: Optional[str]
    zone_avg_price_sqm: Optional[float]

    # Financial Sanity
    is_financially_viable: bool

    # Vision Outputs (populated only if viable)
    condition_tier: Optional[str]
    estimated_renovation_eur: Optional[float]
    visible_flaws: List[str]

    # Final Output
    deal_score: Optional[float]
    should_notify: bool
```

---

## Stage 1: Email Ingestion — DONE

- [x] IMAP listener (`src/email_listener/listener.py`)
- [x] HTML parsing + listing URL extraction (`src/email_listener/parsers.py`)
- [x] SQLite storage + deduplication (`src/email_listener/db.py`)
- [x] Data models (`src/models/listing.py`)
- [x] Config loader + logging + `.env.template`
- [ ] Verify real alerts land in Zoho inbox (waiting on live portal alerts)

## Stage 2: Extraction & Enrichment

Fetch each listing page and extract structured metadata with pure code.
This is the highest-risk layer — portal HTML changes. Flexible selectors + multiple passes.

- [x] Create `src/extractor/` package
- [x] Page fetcher with 405-block evasion, conservative delays, browser-like Headers
- [x] Extract prices + surface area from `og:description`, JSON-LD, and `<script>` data blocks
- [x] Extract image URLs (og:image, gallery scripts, CDN patterns)
- [x] Extract lat/long from `<script>` tags / JSON-LD geo coordinates
- [x] Parse title + description text into state fields
- [x] ~~Web scraper (Playwright/stealth)~~ — deferred; email alerts only per Pattern A
- [x] Store raw HTML + metadata in SQLite (new `listing_pages` table)

## Stage 3: Zone Verification

Code-first geospatial check; LLM only as fallback.

- [ ] Create `src/geocoding/` package
- [ ] Obtain/produce Bucharest zone boundaries as GeoJSON (neighborhood polygons)
- [ ] Shapely point-in-polygon: `canonical_zone` + `zone_avg_price_sqm` (~10ms, $0)
- [ ] Zone ceiling price table (per-zone avg EUR/sqm) seeded + configurable
- [ ] If no coordinates: gpt-4o-mini fallback to extract street name from text
- [ ] Store zone result in `ListingState` + DB

## Stage 4: Early-Exit Filter

Deterministic math gate — no vision spend for obvious dumps.

- [ ] Implement `is_financially_viable`: asking price/sqm > zone ceiling × 1.30 → reject
- [ ] Optional second gate: price/sqm far below floor → flag for manual review (possible scam)
- [ ] Wire as LangGraph conditional edge `should_evaluate`

## Stage 5: Vision Evaluation

One structured multimodal inference per surviving listing. Not an agent — an API call.

- [ ] Create `src/vision_evaluator/evaluator.py` + `prompts.py`
- [ ] Single inference pass over 5–15 images (gemini-1.5-flash primary, gpt-4o-mini fallback)
- [ ] Rigid JSON schema output:
  - `condition_tier`: needs_total_renovation / habitable_dated / renovated_standard / luxury
  - `estimated_renovation_eur_per_sqm`
  - `heating_type_visible`, `window_type`
  - `deal_breakers[]`, `image_score`
- [ ] Retry + exponential backoff on API rate limits
- [ ] Image quality validation + skip broken images

## Stage 6: Valuation & Deal Scoring

Pure arithmetic.

- [ ] `adjusted_price_per_sqm = (price + est_renovation) / sqm`
- [ ] Compare vs `zone_avg_price_sqm` → `discount_percentage`
- [ ] `is_deal = discount_percentage > deal_threshold`
- [ ] `deal_score` (configurable weighted blend of discount + condition tier)

## Stage 7: Notification Dispatch

Plain HTTP POST webhook.

- [ ] Telegram bot: sendMessage + photo attachment (first image)
- [ ] Message formatting: title, zone, price/sqm, adjusted price, discount %, deal score, link
- [ ] WhatsApp integration later (optional)

## Stage 8: Orchestration (LangGraph)

- [ ] Add `langgraph` + `shapely` + `google-genai` deps to pyproject
- [ ] Implement `ListingState` TypedDict (shared state)
- [ ] Implement nodes: extract → verify_zone → financial_sanity → vision → value → notify
- [ ] Conditional edge: `should_evaluate` → vision or END
- [ ] Database-backed persistence of final result per listing
- [ ] Main entry: `src/pipeline.py` consuming DB `status='new'` listings, feeding the graph

## Stage 9: Testing, Deployment, Monitoring

- [ ] Unit tests: parsers, coordinate extraction, shapely zone math, valuation formula
- [ ] Integration test: mock listing → full graph run (mock vision)
- [ ] End-to-end: real alert email → live vision → Telegram
- [ ] Run on schedule (cron/systemd): poll inbox → process new listings
- [ ] Structured logging + error alerts (Telegram on pipeline failure)
- [ ] Scope grading/compare tooling for manual review of vision accuracy
- [ ] User guide + troubleshooting docs

---

## Dependencies / Tools

- Zoho Mail IMAP (imap.zoho.eu) — configured live
- OpenAI: gpt-4o-mini (vision + zone fallback); Gemini 1.5 Flash (primary vision, cheap)
- LangGraph, Shapely, BeautifulSoup, Pydantic
- GeoJSON zone boundaries for Bucharest (hand-curated / OSM)
- Telegram bot token
- SQLite (existing)

## Budget (Pattern A — no proxy/scraper spend)

- Vision: ~$0.0005–0.002 per listing (only for listings that pass early exit)
- Zone fallback: ~$0 negligible
- Hosting: ~$5–20/mo VPS (or run on the dev machine)
- **Total: well under $25/mo** — dramatically cheaper than the original $100–150 projection

## Success Metrics

1. **Extraction**: ≥90% of alert listings enriched with correct price/sqm/coords
2. **Zone match**: ≥95% canonical-zone assignment with code path
3. **Early-exit efficiency**: ≥40% of listings rejected before vision spend
4. **Vision accuracy**: ≥85% condition tier agreed by manual review
5. **Deal quality**: ≥70% of alerted listings worth a site visit
6. **Processing time**: eyes-on alert in < 5 min per listing

## Next Steps

1. ~~Start **Stage 2: Extraction & Enrichment**~~ — implemented; validate multi-pass parsers against real pages once live alert URLs flow in
2. Meanwhile configure real portal alert emails to exercise Stage 1 live
3. Build Stage 3–4 (zone verification + early exit) — pure code, no API keys needed beyond current
4. Wire LangGraph orchestration (Stage 8) incrementally as nodes land
# Real Estate AI Agent - CLAUDE.md

## Project Overview

This project builds an automated deal-finder that evaluates property condition through photos by solving two key engineering challenges:
1. Reliable data extraction without getting IP-banned or flagged by anti-bot systems
2. Structured multimodal evaluation of listing images

## Architecture Overview

```
[ Saved Search Alerts / Local CDP Script ]
                   │
                   ▼
       [ Extract Listing Metadata ]
       - Price, Location, Sqm, Link
       - Image CDN URLs
                   │
                   ▼
       [ Multimodal AI Evaluator ]
       - Inspects 5–15 photos per property
       - Outputs structured condition score + repair budget
                   │
                   ▼
       [ Valuation / Deal Calculator ]
       - Calculates Adjusted Price/sqm
       - Compares against target zone average
                   │
                   ▼
    [ Telegram / WhatsApp Alert to You ]
```

## Data Collection Strategies

### Pattern A: Email Alerts (Most Reliable)
- Set up saved search alerts on Romanian portals (Imobiliare.ro, Storia.ro, OLX.ro, Publi24)
- Backend listens via IMAP/Gmail API for new alert emails
- Extracts listing URLs and accesses individual pages at low volume
- Avoids behavioral blocks from anti-bot systems

### Pattern B: Local Session Automation
- Chrome DevTools Protocol (CDP) with puppeteer.connect/playwright.chromium.connectOverCDP
- Browser extension that parses DOM when user browses
- Runs inside authenticated browser with valid cookies

### Pattern C: Headless Browser Fingerprint Masking
- Playwright with stealth patches (playwright-stealth)
- Puppeteer-Extra with stealth plugins
- Residential proxies (not datacenter IPs)
- Conservative request rates (5-15 seconds between fetches)

## Vision Pipeline for Romanian Real Estate

### Key Visual Indicators
- **Finishes & Renovation Quality**: Flooring (parquet vs laminate), joinery (wood vs PVC), bathroom/kitchen updates
- **Heating System**: Gas boilers vs district heating (termoficare/RADET)
- **Layout & Light**: Structural columns, ceiling heights, window-to-wall ratio
- **Red Flags**: Water stains, mold, outdated fuse boxes, cracked structures

### Example Output Schema
```json
{
  "condition_tier": "needs_total_renovation | habitable_dated | renovated_standard | luxury",
  "estimated_renovation_cost_eur_per_sqm": 250,
  "heating_type_visible": "gas_boiler | district_radiators | unknown",
  "window_type": "modern_pvc | old_wood",
  "deal_breakers": ["visible_moisture_stains", "outdated_fuse_box"],
  "image_score": 7.5,
  "reasoning": "Bathroom requires complete renovation; kitchen appears functional. Central heating unit identified on balcony wall."
}
```

## Implementation Plan

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for detailed step-by-step implementation.

## Technology Stack

- **Python 3.10+**
- **Web Scraping**: BeautifulSoup, Playwright, Puppeteer
- **Email Processing**: imaplib, Gmail API
- **Vision AI**: GPT-4o-mini, Gemini 1.5 Flash
- **Notifications**: Telegram Bot API, WhatsApp Business API
- **Proxies**: Residential proxy providers
- **Scheduling**: Celery or APScheduler

## Configuration

### Environment Variables

```bash
# Email configuration
EMAIL_USER="your@email.com"
EMAIL_PASSWORD="your-password-or-app-specific-password"
IMAP_SERVER="imap.gmail.com"

# Vision API keys
OPENAI_API_KEY="sk-..."
GOOGLE_AI_API_KEY="AIza..."

# Notification tokens
TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TELEGRAM_CHAT_ID="987654321"

# Proxy configuration
PROXY_URL="http://user:pass@proxy-server:8080"

# Target search parameters
TARGET_CITY="Bucharest"
MAX_PRICE_EUR=150000
MIN_SQM=50
```

## Running the System

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start the email listener
python src/email_listener.py

# Start the vision evaluator worker
python src/vision_evaluator.py

# Start the notification service
python src/notification_service.py
```

### Production

```bash
# Use systemd or docker-compose for production deployment

# Example docker-compose.yml
version: '3'
services:
  email-listener:
    build: .
    command: python src/email_listener.py
    env_file: .env
    restart: always
  
  vision-evaluator:
    build: .
    command: python src/vision_evaluator.py
    env_file: .env
    restart: always
  
  notification-service:
    build: .
    command: python src/notification_service.py
    env_file: .env
    restart: always
```

## Monitoring and Logging

- **Logging**: Structured JSON logs with ELK stack
- **Monitoring**: Prometheus + Grafana for system metrics
- **Alerting**: Slack/Telegram alerts for system failures

## Testing Strategy

1. **Unit Tests**: Test individual components (email parsing, vision API calls)
2. **Integration Tests**: Test data flow between components
3. **End-to-End Tests**: Simulate full workflow with mock data
4. **Anti-Bot Testing**: Test with different IP addresses and user agents

## Data Privacy and Compliance

- Respect robots.txt and terms of service
- Implement rate limiting to avoid overwhelming servers
- Store only necessary listing data
- Comply with GDPR for any personal data collected

## Known Challenges and Mitigations

| Challenge | Mitigation Strategy |
|-----------|---------------------|
| IP Banning | Use residential proxies, rotate IPs, implement conservative delays |
| CAPTCHAs | Fall back to email alerts or local browser automation |
| API Rate Limits | Implement exponential backoff, batch requests |
| Image CDN Blocks | Download images directly from CDN URLs (less restricted) |
| Changing Website Structure | Implement flexible CSS selectors, monitor for changes |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Open a pull request with description

## License

[Specify license - MIT/Apache/GPL]

## Contact

Project maintainer: [Your Name]
Email: [Your Email]

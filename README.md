<p align="center">
  <a href="https://brightdata.com/">
    <img src="https://mintlify.s3.us-west-1.amazonaws.com/brightdata/logo/light.svg" width="300" alt="Bright Data Logo">
  </a>
</p>

# Real Estate AI Agent

An automated deal-finder that evaluates property condition through photos from Romanian real estate portals.

## Features

- Email alert-based data collection (avoids anti-bot systems)
- Multimodal AI evaluation of property images
- Automated deal detection based on price and condition
- Telegram/WhatsApp notifications for promising deals

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd real-estate-ai-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.template .env
# Edit .env with your configuration
```

## Configuration

See `.env.template` for required environment variables.

## Running

```bash
# Start email listener
python src/email_listener/main.py

# Start vision evaluator
python src/vision_evaluator/main.py

# Start notification service
python src/notification_service/main.py
```

## Documentation

- [CLAUDE.md](CLAUDE.md) - Complete project documentation
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) - Detailed implementation plan

## License

MIT

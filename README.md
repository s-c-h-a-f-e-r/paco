# Jardín — AI Business Assistant for Landscaping

Bilingual AI assistant for Jaime's landscaping business. Jaime speaks Spanish, clients speak English. Jardín handles the translation and tracks everything.

## Features

- **Bilingual chat**: Spanish with Jaime, English with clients
- **Client memory**: Stores preferences, property notes, service history
- **Price book**: Learns pricing from conversations
- **Extras tracking**: Logs additional services per client
- **Invoice generation**: Quarterly PDF invoices

## Setup

```bash
cd ~/projects/jardin
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
python -m app.main
```

Then open http://localhost:8000

## Tech Stack

- **Backend**: Python + FastAPI
- **Database**: SQLite
- **AI**: Claude API (Anthropic)
- **Frontend**: Vanilla HTML/CSS/JS

## Project Structure

```
jardin/
 app/
    main.py          # FastAPI app
    database.py      # SQLite models
    ai.py            # Claude integration
    invoice.py       # Invoice generation
    static/          # Frontend files
 data/
    jardin.db        # SQLite database
 requirements.txt
```

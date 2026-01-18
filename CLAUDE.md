# Jardín — Project Context

*Last updated: Jan 17, 2026*

## What This Is

A bilingual AI business assistant for Jaime, David's dad. Jaime runs a landscaping company in Santa Cruz, CA. He speaks Spanish; most clients speak English. Jardín bridges the gap.

## The Problem

Jaime has 6 workers (3 maintenance, 3 landscaping) but all the client knowledge lives in his head:
- How each client likes their work done
- What's included in maintenance vs. what's extra
- Pricing for various services

He needs an English-speaking intermediary he can explain things to in Spanish, who then communicates with clients.

## What We Built

### Core Features (Working)
- **Bilingual chat**: Jaime speaks Spanish, AI responds in Spanish, generates English messages for clients
- **Client management**: Create clients via chat or manually
- **Price book**: Learns pricing from conversations
- **Proposals/Quotes**: Generate PDF proposals for clients
- **Invoices**: Quarterly invoicing with extras
- **Message queue**: Pending messages to clients (ready for Twilio integration)

### Tech Stack
- **Backend**: Python + FastAPI
- **Database**: SQLite (data persists in `data/jardin.db`)
- **AI**: Claude API (Anthropic)
- **Frontend**: Vanilla HTML/CSS/JS
- **PDFs**: ReportLab

## How to Run

```bash
cd ~/projects/jardin
source venv/bin/activate
python -m app.main  # Reads API keys from .env file
```

Then open http://localhost:8000

## Current State

### Working
- Chat in Spanish → AI understands and responds
- Client creation from chat (mention name + address + phone)
- Manual client creation via UI
- Proposal PDF generation
- Invoice PDF generation
- Price book learning
- Conversation history persists

### Test Data in DB
- 1 client: Maria Garcia (456 Pine Street, 831-555-1234)
- 1 proposal: PROP-202601-001 ($170)

## Next Steps (Not Yet Built)

1. **Twilio Integration**: Actually send SMS to clients (currently simulated)
2. **Voice Input**: Let Jaime speak instead of type (would need Whisper or similar)
3. **WhatsApp Integration**: Many clients may prefer WhatsApp
4. **Worker Checklists**: Send job lists to workers, receive completion photos
5. **Project Financials**: Track costs/income for landscape projects
6. **Plan Interpretation**: Upload landscape plans, AI explains them

## File Structure

```
jardin/
 app/
    main.py          # FastAPI routes
    database.py      # SQLite models
    ai.py            # Claude integration + response parsing
    invoice.py       # PDF generation (invoices + proposals)
    static/
        index.html   # Main UI
        style.css    # Styling
        app.js       # Frontend logic
 data/
    jardin.db        # SQLite database
    invoices/        # Generated invoice PDFs
    proposals/       # Generated proposal PDFs
 venv/                # Python virtual environment
 requirements.txt
 .env                 # API keys (gitignored)
 CLAUDE.md           # This file
```

## Key Design Decisions

1. **Conversation-first**: No complex forms. Jaime just talks to it.
2. **AI extracts structure**: Client info, prices, proposals parsed from natural conversation
3. **Learns over time**: Price book grows as Jaime quotes services
4. **Spanish UI**: All labels and prompts in Spanish
5. **Simple tech**: No React, no complex build. Just works.

## About Jaime

- Mid-60s, from Oaxaca, Mexico
- Lives in Santa Cruz, CA
- Clients around the Bay Area
- Limited English, primarily Spanish
- Uses iPhone and MacBook Air
- Currently uses Google Docs for invoicing (no QuickBooks)
- Uses Spanglish naturally: "weir" (weed eater), "bushes", "pruning"

## Maintenance vs. Landscaping

Two types of work:
1. **Maintenance**: Recurring (grass, weed eating, blowing, pruning) — quarterly billing
2. **Landscaping**: Projects (needs someone to read plans, manage crew)

The AI assistant primarily helps with maintenance client communication. Landscaping projects need an on-site foreman.

---

## Technical Deep Dive

### AI Response Parsing (app/ai.py)

The AI outputs tagged blocks that get parsed into structured data:

```
[CLIENTE NUEVO]
Nombre: John Smith
Teléfono: 831-555-1234
Dirección: 123 Oak Street
Notas: Likes low water plants
[FIN CLIENTE]

[MENSAJE PARA CLIENTE: John Smith]
Hi John, this is Jaime's Landscaping. We can come by Tuesday to look at your irrigation system.
[FIN MENSAJE]

[SERVICIO REGISTRADO]
Cliente: John Smith
Servicio: Tree trimming
Precio: $120
[FIN SERVICIO]

[PROPUESTA]
Cliente: John Smith
Servicios:
- Tree trimming: $120
- Sprinkler repair: $25
Total: $145
Notas: Includes cleanup
[FIN PROPUESTA]
```

These get extracted via regex and saved to the database automatically.

### Database Schema (app/database.py)

**clients**: id, name, phone, email, address, language, preferences (JSON), maintenance_package (JSON), notes

**services**: id, client_id, description, description_es, price, service_date, invoiced, invoice_id, notes

**price_book**: id, service_type, service_type_es, default_price, notes, times_used

**invoices**: id, client_id, invoice_number, period_start, period_end, subtotal, total, status, pdf_path

**proposals**: id, client_id, proposal_number, services (JSON), subtotal, total, notes, status, pdf_path, valid_until

**conversation_memory**: id, role ('jaime' or 'assistant'), content, metadata (JSON)

**client_messages**: id, client_id, direction, content, status, sent_at

### API Endpoints (app/main.py)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serve main UI |
| `/api/chat` | POST | Process chat message |
| `/api/clients` | GET | List all clients |
| `/api/clients` | POST | Create client |
| `/api/clients/{id}` | GET | Get specific client |
| `/api/clients/{id}/services` | GET | Get client's services |
| `/api/services` | POST | Add service |
| `/api/prices` | GET | Get price book |
| `/api/messages/pending` | GET | Get pending messages |
| `/api/messages/{id}/send` | POST | Mark message sent |
| `/api/invoices` | POST | Generate invoice |
| `/api/invoices/{number}/pdf` | GET | Download invoice PDF |
| `/api/proposals` | GET | List proposals |
| `/api/proposals` | POST | Create proposal |
| `/api/proposals/{id}/pdf` | GET | Download proposal PDF |
| `/api/conversation` | GET | Get chat history |

---

## User Requirements (Jaime's Own Words)

### In Spanish (Original)
> "Lo que me gustaría a mí es controlar el negocio. Tener un orden de mis clientes y de las propuestas."

> "El problema que yo tengo es que yo conozco a cada cliente, sé cómo les gusta su trabajo, pero mis trabajadores no lo saben."

> "Una persona que hablara inglés, yo le podría explicar cómo es el trabajo, y él tendría que hablar con cada cliente. Eso sería magnífico."

### Key Insights
- He knows every client personally
- Workers don't have this knowledge
- Dream: An English-speaking intermediary he can explain things to in Spanish
- Maintenance = quarterly recurring
- Extras = tree trimming ($120), sprinkler repair ($25), valve replacement
- Can't read landscape plans (needs help interpreting)
- No accounting software — just Google Docs

---

## Session History

### Jan 17, 2026 (Evening)
- Built initial prototype
- Fixed several bugs (Python 3.14 incompatibility, env loading, variable naming)
- Added client creation from chat
- Added proposal PDF generation
- Added invoice PDF generation
- Created this context file
- **Next planned**: Twilio SMS integration (for mobile-first experience)

---

## Known Issues

1. **Env loading**: The `.env` file doesn't always load properly. Workaround: pass API key directly on command line.
2. **Server cleanup**: Sometimes need to `pkill -9 -f "python -m app.main"` to clear old processes.
3. **Mobile UX**: Current UI is functional but not optimized for mobile. Jaime will use iPhone primarily.

---

## Future Vision

**Phase 1 (Current)**: Web chat interface, PDF proposals/invoices
**Phase 2**: Twilio SMS — Jaime texts the app from iPhone
**Phase 3**: Voice input — Jaime speaks instead of types
**Phase 4**: Worker integration — checklists, photo verification
**Phase 5**: Project accounting — track landscaping project P&L

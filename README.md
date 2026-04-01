# Bookly Customer Support Agent

AI-powered customer support agent for Bookly, a fictional online bookstore. Built with FastAPI and the OpenAI API, it demonstrates tool-calling, deterministic business logic, and real API orchestration (Google Books) in a single conversational agent.



https://github.com/user-attachments/assets/3736899f-2f9e-4916-9020-2641495ff1fa



https://github.com/user-attachments/assets/c72f6cfe-4280-481e-826d-e28b2b8d3056



## Prerequisites

- Python 3.9+
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/your-username/bookly-chat.git
cd bookly-chat
```

**2. Create and activate a virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate       # Mac/Linux
venv\Scripts\activate          # Windows
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Add your OpenAI API key**

Create a `.env` file in the project root:
```
OPENAI_API_KEY=your-key-here
```

## Run

```bash
python app.py
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

## Project Structure

```
bookly-chat/
├── app.py            # FastAPI server, chat loop, escalation logic, UI
├── tools.py          # Tool functions: order lookup, returns, book search, escalation
├── mock_data.py      # Mock order database with demo scenarios
├── system_prompt.md  # Agent system prompt (loaded at runtime by app.py)
├── requirements.txt
└── .env              # Not committed — add your own
```

## Demo Order IDs

Use these in the chat to trigger specific scenarios.

| Order ID | Customer | Scenario |
|----------|----------|----------|
| ORD-1001 | Sarah Chen | Delivered 3 days ago — happy path return |
| ORD-1002 | Marcus Johnson | In transit — can check status, return not yet available |
| ORD-1003 | Emily Rodriguez | Delivered 52 days ago — outside 30-day return window |
| ORD-1004 | David Kim | Already returned — duplicate return rejected |
| ORD-1005 | Lisa Patel | Still processing — eligible for cancellation, not return |
| ORD-1006 | James Wright | Delivered 12 days ago — second happy path return |
| ORD-1007 | Nina Okafor | Mixed order — one delivered, one pre-order (releases April 15) |
| ORD-1008 | Amy Torres | Wrong edition received — triggers 3-tool flow: lookup → book search → return |

## Policies

The agent answers these directly without a tool call.

| Policy | Rule |
|--------|------|
| Returns | 30-day window from delivery date |
| Return shipping | Free for defective/wrong items; customer pays otherwise |
| Refunds | 5–10 business days after item received at warehouse |
| Shipping | Standard: 5–7 days · Express: 2–3 days |
| Cancellations | Only before the order ships |
| Pre-orders | Ships within 2 days of release date |
| Password reset | Directed to "Forgot Password" on the login page |
| Payment methods | Visa, Mastercard, American Express, PayPal |

## Architecture Notes

- **Deterministic layer**: Business rules (return eligibility, return window, defect detection) are enforced in Python — the LLM communicates the result but cannot override it.
- **Hard escalation triggers**: Certain keywords (billing fraud, legal threats, account security, safety) are caught in code before the LLM sees the message, forcing an immediate handoff to a human agent.
- **Soft escalation**: A denial counter tracks negative outcomes per session. After 2 denials, the agent is nudged to proactively offer a human handoff.
- **Google Books API**: `search_books` calls the public Google Books API (no key required) for book lookups, edition identification, and recommendations.
- **System prompt**: Loaded from `system_prompt.md` at startup — edit the file and restart to change agent behavior without touching `app.py`.

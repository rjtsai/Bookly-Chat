import os
import json
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from openai import OpenAI
from tools import lookup_order, initiate_return, escalate_to_human, check_escalation_triggers, search_books

app = FastAPI()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

MODEL = "gpt-4o"

# ---- System Prompt ----

with open(os.path.join(os.path.dirname(__file__), "system_prompt.md"), "r") as f:
    SYSTEM_PROMPT = f.read()

# ---- OpenAI Tool Definitions ----

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up order details including status, items, shipping, and delivery information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order ID (format: ORD-XXXX)"
                    }
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_return",
            "description": "Check return eligibility and initiate a return. Enforces business rules: 30-day window, must be delivered, not already returned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order ID (format: ORD-XXXX)"
                    },
                    "reason": {
                        "type": "string",
                        "description": "The customer's reason for returning the item"
                    },
                    "items_to_return": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of book titles the customer wants to return. Omit or leave empty if returning all items."
                    }
                },
                "required": ["order_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Transfer the conversation to a human support agent when the issue is outside scope or the customer is dissatisfied.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief summary of why the conversation is being escalated"
                    },
                    "conversation_summary": {
                        "type": "string",
                        "description": "Summary of the conversation so far for the human agent"
                    }
                },
                "required": ["reason", "conversation_summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_books",
            "description": "Search for books by title, author, ISBN, or topic. Use to find specific editions, recommend similar titles, or verify book details. Useful when a customer asks about availability, wants a recommendation, or needs to identify the correct edition of a book.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — can be a title, author name, ISBN, or descriptive query like 'science fiction similar to Dune'"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (1-5, default 3)"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# ---- Tool Dispatch ----

TOOL_FUNCTIONS = {
    "lookup_order": lookup_order,
    "initiate_return": initiate_return,
    "escalate_to_human": escalate_to_human,
    "search_books": search_books,
}


def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool function and return the result as a JSON string."""
    func = TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = func(**arguments)
    return json.dumps(result, default=str)


# ---- Chat Logic ----

# In-memory conversation store (keyed by session — single session for prototype)
conversation_history = []
denial_counter = 0

# Tool results that count as negative outcomes for the soft escalation counter
DENIAL_REASONS = {"order_not_shipped", "order_in_transit", "already_returned", "outside_return_window"}


def _build_conversation_summary() -> str:
    """Produce a plain-text summary of conversation history for escalation context."""
    lines = []
    for msg in conversation_history:
        role = "Customer" if msg["role"] == "user" else "Agent"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines) if lines else "No prior conversation."


def chat(user_message: str) -> str:
    """
    Process a user message through the agent loop.
    Handles multi-turn tool calling — if the LLM requests a tool,
    we execute it and feed the result back for a final response.

    Two escalation layers run here:
      1. Hard triggers (code) — checked before the LLM sees the message.
      2. Soft escalation nudge — appended to the system prompt when denial_counter >= 2.
    """
    global denial_counter

    conversation_history.append({"role": "user", "content": user_message})

    # --- Layer 1: Hard escalation trigger check ---
    trigger = check_escalation_triggers(user_message)
    if trigger:
        print(f"  [Hard Escalation] category={trigger['trigger_category']} matched='{trigger['trigger_matched']}'")
        injection = (
            f"MANDATORY ESCALATION: The customer's message triggered a mandatory escalation "
            f"for category '{trigger['trigger_category']}' (matched: \"{trigger['trigger_matched']}\"). "
            f"You MUST call the escalate_to_human tool immediately. Acknowledge the customer's concern "
            f"empathetically and let them know you're connecting them with a specialist who can help."
        )
        system_message = SYSTEM_PROMPT + "\n\n" + injection
    else:
        system_message = SYSTEM_PROMPT

    # --- Layer 2: Soft escalation nudge ---
    if denial_counter >= 2:
        system_message += (
            "\n\nNOTE: The customer has encountered multiple issues or denials in this conversation. "
            "Proactively offer to connect them with a human agent."
        )

    messages = [{"role": "system", "content": system_message}] + conversation_history

    # Agent loop: keep going until the LLM gives a final text response
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        message = response.choices[0].message

        # If no tool calls, we have our final response
        if not message.tool_calls:
            assistant_reply = message.content
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            return assistant_reply

        # Process tool calls
        # Add the assistant's message (with tool_calls) to the conversation
        messages.append(message)

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            print(f"  [Tool Call] {tool_name}({arguments})")

            tool_result = execute_tool(tool_name, arguments)

            print(f"  [Tool Result] {tool_result[:200]}")

            # Track negative outcomes for soft escalation
            parsed = json.loads(tool_result)
            if not parsed.get("success") and parsed.get("reason") in DENIAL_REASONS:
                denial_counter += 1
                print(f"  [Denial Counter] {denial_counter} (reason: {parsed.get('reason')})")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

    # Loop continues — LLM will now generate a response using the tool results


# ---- API Endpoint ----

@app.post("/chat")
async def chat_endpoint(request: Request):
    body = await request.json()
    user_message = body.get("message", "")
    if not user_message:
        return {"reply": "Please enter a message."}
    reply = chat(user_message)
    return {"reply": reply}


@app.post("/reset")
async def reset_endpoint():
    global denial_counter
    conversation_history.clear()
    denial_counter = 0
    return {"status": "Conversation reset."}


# ---- Simple Chat UI ----

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bookly Support</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f0;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 20px;
            gap: 20px;
            min-height: 100vh;
        }
        .sidebar {
            width: 220px;
            flex-shrink: 0;
            background: white;
            border-radius: 12px;
            padding: 20px;
            position: sticky;
            top: 20px;
            max-height: 95vh;
            overflow-y: auto;
        }
        .sidebar h2 {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #999;
            margin-bottom: 14px;
        }
        .order-card {
            padding: 10px 12px;
            border-radius: 8px;
            border: 1px solid #eee;
            margin-bottom: 8px;
        }
        .order-card:last-child { margin-bottom: 0; }
        .order-id {
            font-size: 13px;
            font-weight: 600;
            color: #1a1a2e;
            font-family: monospace;
            margin-bottom: 4px;
        }
        .order-customer {
            font-size: 12px;
            color: #555;
            margin-bottom: 3px;
        }
        .order-desc {
            font-size: 11px;
            color: #999;
            line-height: 1.4;
        }
        .container {
            width: 100%;
            max-width: 680px;
            display: flex;
            flex-direction: column;
            height: 95vh;
        }
        .header {
            background: #1a1a2e;
            color: white;
            padding: 20px 24px;
            border-radius: 12px 12px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { font-size: 18px; font-weight: 600; }
        .header .subtitle { font-size: 12px; opacity: 0.7; margin-top: 2px; }
        .reset-btn {
            background: rgba(255,255,255,0.15);
            border: none;
            color: white;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        .reset-btn:hover { background: rgba(255,255,255,0.25); }
        .chat-window {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: white;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .message {
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 14px;
            line-height: 1.5;
            white-space: pre-wrap;
        }
        .user {
            align-self: flex-end;
            background: #1a1a2e;
            color: white;
            border-bottom-right-radius: 4px;
        }
        .assistant {
            align-self: flex-start;
            background: #f0f0f0;
            color: #1a1a1a;
            border-bottom-left-radius: 4px;
        }
        .typing {
            align-self: flex-start;
            background: #f0f0f0;
            color: #999;
            font-style: italic;
        }
        .input-area {
            display: flex;
            gap: 10px;
            padding: 16px 20px;
            background: white;
            border-top: 1px solid #eee;
            border-radius: 0 0 12px 12px;
        }
        .input-area input {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            outline: none;
        }
        .input-area input:focus { border-color: #1a1a2e; }
        .input-area button {
            padding: 12px 24px;
            background: #1a1a2e;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }
        .input-area button:disabled { opacity: 0.5; cursor: not-allowed; }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2>Demo Order IDs</h2>
        <div class="order-card">
            <div class="order-id">ORD-1001</div>
            <div class="order-customer">Sarah Chen</div>
            <div class="order-desc">Delivered 3 days ago — within return window. Happy path for returns.</div>
        </div>
        <div class="order-card">
            <div class="order-id">ORD-1002</div>
            <div class="order-customer">Marcus Johnson</div>
            <div class="order-desc">Currently in transit — can check status, but return can't be initiated yet.</div>
        </div>
        <div class="order-card">
            <div class="order-id">ORD-1003</div>
            <div class="order-customer">Emily Rodriguez</div>
            <div class="order-desc">Delivered 52 days ago — outside the 30-day return window. Return will be denied.</div>
        </div>
        <div class="order-card">
            <div class="order-id">ORD-1004</div>
            <div class="order-customer">David Kim</div>
            <div class="order-desc">Already returned — duplicate return request will be rejected.</div>
        </div>
        <div class="order-card">
            <div class="order-id">ORD-1005</div>
            <div class="order-customer">Lisa Patel</div>
            <div class="order-desc">Still processing, not yet shipped — eligible for cancellation, not a return.</div>
        </div>
        <div class="order-card">
            <div class="order-id">ORD-1006</div>
            <div class="order-customer">James Wright</div>
            <div class="order-desc">Delivered 12 days ago — within return window. Second happy path for returns.</div>
        </div>
        <div class="order-card">
            <div class="order-id">ORD-1007</div>
            <div class="order-customer">Nina Okafor</div>
            <div class="order-desc">Mixed order — one book delivered, one on pre-order releasing April 15. Tests pre-order status messaging.</div>
        </div>
        <div class="order-card">
            <div class="order-id">ORD-1008</div>
            <div class="order-customer">Amy Torres</div>
            <div class="order-desc">Wrong edition received — hardcover ordered. Triggers search_books + return flow across three tools in one conversation.</div>
        </div>
    </div>
    <div class="sidebar">
        <h2>Demo Policies</h2>
        <div class="order-card">
            <div class="order-id">Returns</div>
            <div class="order-desc">30-day window from delivery. Free return shipping for defective or wrong items; customer pays for all others.</div>
        </div>
        <div class="order-card">
            <div class="order-id">Refunds</div>
            <div class="order-desc">Processed within 5–10 business days after the returned item is received at the warehouse.</div>
        </div>
        <div class="order-card">
            <div class="order-id">Shipping</div>
            <div class="order-desc">Standard: 5–7 business days. Express: 2–3 business days.</div>
        </div>
        <div class="order-card">
            <div class="order-id">Cancellations</div>
            <div class="order-desc">Only possible before the order ships. Once in transit, the customer must go through the return process.</div>
        </div>
        <div class="order-card">
            <div class="order-id">Pre-orders</div>
            <div class="order-desc">Pre-order items ship within 2 days of their release date. Communicated as a pre-order, never as "processing."</div>
        </div>
        <div class="order-card">
            <div class="order-id">Password Reset</div>
            <div class="order-desc">Agent cannot reset passwords. Directs customers to the "Forgot Password" link on the login page.</div>
        </div>
        <div class="order-card">
            <div class="order-id">Payment Methods</div>
            <div class="order-desc">Visa, Mastercard, American Express, and PayPal.</div>
        </div>
    </div>
    <div class="container">
        <div class="header">
            <div>
                <h1>Bookly Support</h1>
                <div class="subtitle">AI-powered customer support</div>
            </div>
            <button class="reset-btn" onclick="resetChat()">New Chat</button>
        </div>
        <div class="chat-window" id="chat"></div>
        <div class="input-area">
            <input type="text" id="input" placeholder="Type your message..." onkeydown="if(event.key==='Enter')sendMessage()" autofocus>
            <button id="sendBtn" onclick="sendMessage()">Send</button>
        </div>
    </div>
    <script>
        const chatEl = document.getElementById('chat');
        const inputEl = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');

        function addMessage(role, text) {
            const div = document.createElement('div');
            div.className = 'message ' + role;
            div.textContent = text;
            chatEl.appendChild(div);
            chatEl.scrollTop = chatEl.scrollHeight;
            return div;
        }

        async function sendMessage() {
            const msg = inputEl.value.trim();
            if (!msg) return;
            inputEl.value = '';
            sendBtn.disabled = true;
            addMessage('user', msg);
            const typing = addMessage('typing', 'Bookly agent is typing...');
            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: msg})
                });
                const data = await res.json();
                typing.remove();
                addMessage('assistant', data.reply);
            } catch (e) {
                typing.remove();
                addMessage('assistant', 'Sorry, something went wrong. Please try again.');
            }
            sendBtn.disabled = false;
            inputEl.focus();
        }

        async function resetChat() {
            await fetch('/reset', {method: 'POST'});
            chatEl.innerHTML = '';
            addMessage('assistant', "Hi there! Welcome to Bookly support. How can I help you today?");
        }

        // Initial greeting
        addMessage('assistant', "Hi there! Welcome to Bookly support. How can I help you today?");
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
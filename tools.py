from mock_data import ORDERS, TODAY
from datetime import timedelta
from typing import Optional
import requests

ESCALATION_TRIGGERS = {
    "billing": ["charged twice", "double charged", "wrong charge", "billing issue", "unauthorized charge", "fraud"],
    "legal": ["lawyer", "attorney", "legal action", "sue", "lawsuit"],
    "account_security": ["hacked", "someone accessed my account", "unauthorized access", "change my password"],
    "safety": ["injured", "allergic reaction", "hazardous"],
}


def check_escalation_triggers(message: str) -> Optional[dict]:
    """
    Scans a raw customer message for hard escalation triggers.
    Returns None if no trigger matched, or a dict describing the trigger.
    """
    lowered = message.lower()
    for category, keywords in ESCALATION_TRIGGERS.items():
        for keyword in keywords:
            if keyword in lowered:
                return {
                    "should_escalate": True,
                    "trigger_category": category,
                    "trigger_matched": keyword,
                    "message": "This issue requires a specialist. Transferring to our support team.",
                }
    return None

RETURN_WINDOW_DAYS = 30
REFUND_PROCESSING_DAYS = "5–10 business days"


def lookup_order(order_id: str) -> dict:
    """
    Pure data retrieval — no business logic, no judgment calls.
    Returns order details or a clear 'not found' response.
    """
    order_id = order_id.strip().upper()
    order = ORDERS.get(order_id)

    if not order:
        return {
            "success": False,
            "error": f"No order found with ID '{order_id}'. Please verify the order ID and try again."
        }

    # Split items into delivered and pre-order
    delivered_items = []
    pre_order_items = []
    for item in order["items"]:
        label = f"{item['title']} by {item['author']} (x{item['qty']}) — ${item['price']:.2f}"
        if item.get("pre_order"):
            pre_order_items.append({
                "title": item["title"],
                "display": label,
                "release_date": item["release_date"].strftime("%B %d, %Y"),
            })
        else:
            delivered_items.append(label)

    # Build a clean response the LLM can use to craft a natural reply
    result = {
        "success": True,
        "order_id": order_id,
        "customer_name": order["customer_name"],
        "items": delivered_items + [p["display"] + " [PRE-ORDER]" for p in pre_order_items],
        "order_date": order["order_date"].strftime("%B %d, %Y"),
        "shipping_method": order["shipping_method"],
        "status": order["status"],
        "tracking_number": order["tracking_number"],
    }

    if pre_order_items:
        result["pre_order_items"] = pre_order_items

    # Add contextual info based on status
    if order["status"] == "delivered":
        result["delivered_date"] = order["delivered_date"].strftime("%B %d, %Y")
        days_since_delivery = (TODAY - order["delivered_date"]).days
        result["days_since_delivery"] = days_since_delivery
        result["within_return_window"] = days_since_delivery <= RETURN_WINDOW_DAYS
    elif order["status"] == "partial_delivery":
        result["delivered_date"] = order["delivered_date"].strftime("%B %d, %Y")
        days_since_delivery = (TODAY - order["delivered_date"]).days
        result["days_since_delivery"] = days_since_delivery
        result["within_return_window"] = days_since_delivery <= RETURN_WINDOW_DAYS
        result["note"] = "Some items have been delivered. Pre-order items will ship separately within 2 days of their release date."
    elif order["status"] == "in_transit":
        result["estimated_delivery"] = _estimate_delivery(order)
    elif order["status"] == "processing":
        result["note"] = "Order has not shipped yet and is still eligible for cancellation."

    if order["return_status"]:
        result["return_status"] = order["return_status"]

    return result


def initiate_return(order_id: str, reason: str, items_to_return: list = None) -> dict:
    """
    Deterministic return eligibility check + initiation.
    ALL business rules are enforced here — the LLM just communicates the result.
    """
    order_id = order_id.strip().upper()
    order = ORDERS.get(order_id)

    if not order:
        return {
            "success": False,
            "error": f"No order found with ID '{order_id}'."
        }

    # Rule 1: Order must be delivered
    if order["status"] == "processing":
        return {
            "success": False,
            "reason": "order_not_shipped",
            "message": "This order hasn't shipped yet. It can be cancelled instead of returned.",
            "suggestion": "Ask the customer if they'd like to cancel the order."
        }

    if order["status"] == "in_transit":
        return {
            "success": False,
            "reason": "order_in_transit",
            "message": "This order is currently in transit and hasn't been delivered yet.",
            "suggestion": "Let the customer know they can initiate a return after delivery."
        }

    # Rule 2: Can't return something already returned
    if order["return_status"] == "returned":
        return {
            "success": False,
            "reason": "already_returned",
            "message": "This order has already been returned."
        }

    # Rule 3: Must be within 30-day return window
    if order["delivered_date"]:
        days_since_delivery = (TODAY - order["delivered_date"]).days
        if days_since_delivery > RETURN_WINDOW_DAYS:
            return {
                "success": False,
                "reason": "outside_return_window",
                "message": f"This order was delivered {days_since_delivery} days ago, which is outside the 30-day return window.",
                "delivered_date": order["delivered_date"].strftime("%B %d, %Y"),
                "deadline_was": (order["delivered_date"] + timedelta(days=RETURN_WINDOW_DAYS)).strftime("%B %d, %Y")
            }

    # All checks passed — approve the return
    is_defective = _is_defective_reason(reason)

    all_titles = [item["title"] for item in order["items"]]
    returning = items_to_return if items_to_return else all_titles

    return {
        "success": True,
        "return_id": f"RET-{order_id.split('-')[1]}",
        "order_id": order_id,
        "items": returning,
        "reason": reason,
        "return_shipping": "free" if is_defective else "customer_pays",
        "return_shipping_note": (
            "Return shipping is free for defective/damaged items."
            if is_defective
            else "Customer is responsible for return shipping costs."
        ),
        "refund_timeline": REFUND_PROCESSING_DAYS,
        "message": "Return approved. A return shipping label will be sent to the customer's email."
    }


def escalate_to_human(reason: str, conversation_summary: str) -> dict:
    """
    Mock escalation — in production this would create a ticket
    and route to the appropriate support queue.
    """
    return {
        "success": True,
        "ticket_id": "TKT-8842",
        "estimated_wait": "Under 5 minutes",
        "message": "The conversation has been transferred to a human support agent.",
        "context_passed": True
    }


# ---- Internal helpers (not exposed to the LLM) ----

def _estimate_delivery(order: dict) -> str:
    """Estimate delivery based on shipping method and order date."""
    if order["shipping_method"] == "express":
        est = order["order_date"] + timedelta(days=3)
    else:
        est = order["order_date"] + timedelta(days=7)
    return est.strftime("%B %d, %Y")


def _is_defective_reason(reason: str) -> bool:
    """Simple keyword check to determine if return reason indicates a defect."""
    defective_keywords = ["defective", "damaged", "broken", "torn", "ripped", "missing pages", "wrong item", "incorrect", "wrong edition"]
    return any(keyword in reason.lower() for keyword in defective_keywords)


def search_books(query: str, max_results: int = 3) -> dict:
    """
    Search the Google Books API by title, author, ISBN, or natural language query.
    Returns a structured list of matching books with fields relevant to the LLM.
    """
    max_results = min(max(1, max_results), 5)

    try:
        response = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": query, "maxResults": max_results},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return {"success": False, "error": "Could not search books at this time."}

    items = data.get("items", [])
    if not items:
        return {"success": True, "results": [], "message": "No books found matching that query."}

    books = []
    for item in items:
        info = item.get("volumeInfo", {})

        isbn = None
        for identifier in info.get("industryIdentifiers", []):
            if identifier["type"] == "ISBN_13":
                isbn = identifier["identifier"]
                break
        if not isbn:
            for identifier in info.get("industryIdentifiers", []):
                if identifier["type"] == "ISBN_10":
                    isbn = identifier["identifier"]
                    break

        description = info.get("description", "")
        if len(description) > 200:
            description = description[:200].rstrip() + "…"

        books.append({
            "title": info.get("title"),
            "authors": info.get("authors", []),
            "publisher": info.get("publisher"),
            "published_date": info.get("publishedDate"),
            "description": description,
            "isbn": isbn,
            "page_count": info.get("pageCount"),
            "categories": info.get("categories", []),
            "thumbnail_url": info.get("imageLinks", {}).get("thumbnail"),
            "preview_link": info.get("previewLink"),
        })

    return {"success": True, "results": books}
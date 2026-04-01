# Mock Data Design
# Each order is designed to trigger a specific demo scenario

from datetime import datetime, timedelta

# We'll use a fixed "today" for consistent demo behavior
TODAY = datetime(2026, 3, 31)

ORDERS = {
    "ORD-1001": {
        "customer_name": "Sarah Chen",
        "customer_email": "sarah.chen@email.com",
        "items": [
            {"title": "The Midnight Library", "author": "Matt Haig", "price": 14.99, "qty": 1},
            {"title": "Atomic Habits", "author": "James Clear", "price": 16.99, "qty": 1}
        ],
        "order_date": TODAY - timedelta(days=10),
        "shipping_method": "standard",
        "status": "delivered",
        "tracking_number": "BKL-TRK-884721",
        "delivered_date": TODAY - timedelta(days=3),
        "return_status": None
    },

    "ORD-1002": {
        "customer_name": "Marcus Johnson",
        "customer_email": "m.johnson@email.com",
        "items": [
            {"title": "Dune", "author": "Frank Herbert", "price": 12.99, "qty": 1}
        ],
        "order_date": TODAY - timedelta(days=5),
        "shipping_method": "express",
        "status": "in_transit",
        "tracking_number": "BKL-TRK-991035",
        "delivered_date": None,
        "return_status": None
    },

    "ORD-1003": {
        "customer_name": "Emily Rodriguez",
        "customer_email": "e.rodriguez@email.com",
        "items": [
            {"title": "Educated", "author": "Tara Westover", "price": 13.99, "qty": 1},
            {"title": "Becoming", "author": "Michelle Obama", "price": 18.99, "qty": 1},
            {"title": "Where the Crawdads Sing", "author": "Delia Owens", "price": 15.99, "qty": 1}
        ],
        "order_date": TODAY - timedelta(days=60),
        "shipping_method": "standard",
        "status": "delivered",
        "tracking_number": "BKL-TRK-667482",
        "delivered_date": TODAY - timedelta(days=52),
        "return_status": None
    },

    "ORD-1004": {
        "customer_name": "David Kim",
        "customer_email": "d.kim@email.com",
        "items": [
            {"title": "Project Hail Mary", "author": "Andy Weir", "price": 14.99, "qty": 1}
        ],
        "order_date": TODAY - timedelta(days=25),
        "shipping_method": "standard",
        "status": "delivered",
        "tracking_number": "BKL-TRK-553198",
        "delivered_date": TODAY - timedelta(days=18),
        "return_status": "returned"
    },

    "ORD-1005": {
        "customer_name": "Lisa Patel",
        "customer_email": "l.patel@email.com",
        "items": [
            {"title": "The Great Gatsby", "author": "F. Scott Fitzgerald", "price": 9.99, "qty": 2}
        ],
        "order_date": TODAY - timedelta(days=1),
        "shipping_method": "standard",
        "status": "processing",
        "tracking_number": None,
        "delivered_date": None,
        "return_status": None
    },

    "ORD-1006": {
        "customer_name": "James Wright",
        "customer_email": "j.wright@email.com",
        "items": [
            {"title": "Sapiens", "author": "Yuval Noah Harari", "price": 15.99, "qty": 1}
        ],
        "order_date": TODAY - timedelta(days=15),
        "shipping_method": "express",
        "status": "delivered",
        "tracking_number": "BKL-TRK-772340",
        "delivered_date": TODAY - timedelta(days=12),
        "return_status": None
    },

    "ORD-1008": {
        "customer_name": "Amy Torres",
        "customer_email": "a.torres@email.com",
        "items": [
            {"title": "Educated", "author": "Tara Westover", "format": "hardcover", "price": 22.99, "qty": 1}
        ],
        "order_date": TODAY - timedelta(days=8),
        "shipping_method": "standard",
        "status": "delivered",
        "tracking_number": "BKL-TRK-441298",
        "delivered_date": TODAY - timedelta(days=2),
        "return_status": None
    },

    "ORD-1007": {
        "customer_name": "Nina Okafor",
        "customer_email": "n.okafor@email.com",
        "items": [
            {"title": "The Thursday Murder Club", "author": "Richard Osman", "price": 14.99, "qty": 1},
            {"title": "Intermezzo", "author": "Sally Rooney", "price": 19.99, "qty": 1,
             "pre_order": True, "release_date": datetime(2026, 4, 15)},
        ],
        "order_date": TODAY - timedelta(days=8),
        "shipping_method": "standard",
        "status": "partial_delivery",
        "tracking_number": "BKL-TRK-334901",
        "delivered_date": TODAY - timedelta(days=2),
        "return_status": None
    }
}

# ---- DEMO SCENARIO MAPPING ----
#
# ORD-1001 (Sarah)    → Happy path: delivered recently, eligible for return
# ORD-1002 (Marcus)   → In transit: can check status, can't return yet
# ORD-1003 (Emily)    → Delivered 52 days ago: OUTSIDE 30-day return window → denial
# ORD-1004 (David)    → Already returned: return request should be rejected (duplicate)
# ORD-1005 (Lisa)     → Processing / not shipped: can cancel, can't return
# ORD-1006 (James)    → Delivered 12 days ago: eligible for return, good second happy path
# ORD-1007 (Nina)     → Mixed order: one book delivered, one on pre-order (releases April 15)
# ORD-1008 (Amy)      → Wrong edition received: hardcover ordered, triggers search_books + return flow
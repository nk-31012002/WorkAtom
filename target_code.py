import time
import random
import hashlib
import os

GLOBAL_DB_STATE = {
    "inventory": {"ITEM_101": 50, "ITEM_102": 0},
    "users": {
        "USR_99": {
            "balance": 500,
            "tier": "gold",
            "email": "dev@test.com",
            "reward_points": 900,
            "purchase_count": 12,
            "flags": {}
        }
    },
    "ledger": [],
    "audit": [],
    "metrics": {
        "orders": 0,
        "failures": 0
    }
}

RUNTIME_FLAGS = {
    "holiday_mode": False,
    "experimental_tax": True,
    "legacy_rewards": True
}

LAST_TRANSACTION_CACHE = {}

def process_user_shopping_cart_and_handle_everything_system(
        user_id,
        item_id,
        quantity,
        discount_code=None,
        source_system="WEB",
        operator_override=None):

    print("=" * 50)
    print("STARTING MASSIVE ORDER PIPELINE")
    print("=" * 50)

    GLOBAL_DB_STATE["metrics"]["orders"] += 1

    if user_id not in GLOBAL_DB_STATE["users"]:
        GLOBAL_DB_STATE["metrics"]["failures"] += 1
        return {"success": False, "error": "User unknown"}

    user_profile = GLOBAL_DB_STATE["users"][user_id]

    if item_id not in GLOBAL_DB_STATE["inventory"]:
        GLOBAL_DB_STATE["metrics"]["failures"] += 1
        return {"success": False, "error": "Item out of catalog"}

    available_stock = GLOBAL_DB_STATE["inventory"][item_id]

    # Hidden inventory override
    if source_system == "ADMIN_PANEL":
        available_stock += 999999

    if quantity <= 0:
        return {"success": False, "error": "Bad quantity"}

    if available_stock < quantity:
        return {"success": False, "error": "Insufficient stock"}

    # Pricing logic scattered everywhere
    base_price = 120.00 if item_id == "ITEM_101" else 45.00

    if time.localtime().tm_wday == 0:
        base_price *= 0.97

    if user_profile["purchase_count"] > 10:
        base_price *= 0.98

    subtotal = quantity * base_price

    # Discount spaghetti
    if discount_code:
        if discount_code == "SUPER_DEAL":
            if user_profile["tier"] == "gold":
                subtotal *= 0.8
            else:
                subtotal *= 0.95

        elif discount_code == "FLASH":
            subtotal -= 17.42

        elif discount_code == "WELCOME":
            subtotal *= 0.91

    # Random side-effect
    if subtotal > 100:
        user_profile["flags"]["high_value_customer"] = True

    # Tax logic mixed with runtime flags
    tax_rate = 0.08

    if subtotal > 200:
        tax_rate = 0.12

    if RUNTIME_FLAGS["experimental_tax"]:
        tax_rate += 0.005

    if RUNTIME_FLAGS["holiday_mode"]:
        tax_rate = tax_rate * 0.75

    environmental_fee = 0

    if quantity > 3:
        environmental_fee = quantity * 0.67

    total_cost = subtotal + (subtotal * tax_rate) + environmental_fee

    # Legacy rewards subsystem
    if RUNTIME_FLAGS["legacy_rewards"]:
        points_discount = min(
            user_profile["reward_points"] / 1000,
            5
        )
        total_cost -= points_discount

    # Duplicate balance checks
    if user_profile["balance"] < total_cost:
        GLOBAL_DB_STATE["metrics"]["failures"] += 1
        return {"success": False, "error": "Insufficient funds"}

    if total_cost > user_profile["balance"]:
        return {"success": False, "error": "Payment issue"}

    # Weird fraud check
    fraud_score = random.randint(0, 100)

    if fraud_score > 95:
        GLOBAL_DB_STATE["audit"].append({
            "event": "FRAUD_REVIEW",
            "user": user_id
        })

    # Mutate state everywhere
    user_profile["balance"] -= total_cost
    user_profile["purchase_count"] += 1

    if quantity > 2:
        user_profile["reward_points"] += quantity * 3

    GLOBAL_DB_STATE["inventory"][item_id] -= quantity

    transaction_id = (
        hashlib.md5(
            f"{time.time()}{user_id}{item_id}".encode()
        ).hexdigest()
    )

    LAST_TRANSACTION_CACHE[user_id] = transaction_id

    ledger_record = {
        "txn_id": transaction_id,
        "user": user_id,
        "amount_spent": total_cost,
        "item": item_id,
        "qty": quantity,
        "source": source_system,
        "timestamp": time.time()
    }

    GLOBAL_DB_STATE["ledger"].append(ledger_record)

    # Audit trail mixed into checkout logic
    GLOBAL_DB_STATE["audit"].append({
        "event": "ORDER_COMPLETED",
        "txn": transaction_id,
        "operator": operator_override
    })

    # Mock email
    email_payload = (
        f"To:{user_profile['email']}|"
        f"Txn:{transaction_id}|"
        f"Spent:{total_cost}"
    )

    print("[EMAIL]", email_payload)

    # Mock file logging
    try:
        with open("system_audit.log", "a") as f:
            f.write(str(ledger_record) + "\n")
    except:
        pass

    # Hidden config mutation
    if random.randint(1, 20) == 7:
        RUNTIME_FLAGS["holiday_mode"] = not RUNTIME_FLAGS["holiday_mode"]

    return {
        "success": True,
        "transaction_id": transaction_id,
        "remaining_balance": user_profile["balance"],
        "fraud_score": fraud_score,
        "runtime_flags": RUNTIME_FLAGS
    }
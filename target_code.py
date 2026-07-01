import time
import random
import hashlib
import uuid
from dataclasses import dataclass, field


# ============================================================
# SERVICE LOCATOR
# ============================================================

class Container:
    _services = {}

    @classmethod
    def register(cls, name, service):
        cls._services[name] = service

    @classmethod
    def resolve(cls, name):
        return cls._services[name]


# ============================================================
# EXECUTION CONTEXT
# ============================================================

@dataclass
class OrderContext:
    customer_id: str
    sku: str
    quantity: int
    promo: str = None
    source: str = "WEB"
    operator: str = None

    customer: dict = None
    reserve_snapshot: dict = None
    pricing: object = None
    tax: float = 0
    total: float = 0
    risk: object = None
    payment_ok: bool = False
    order_id: str = None
    fulfillment_id: str = None

    metadata: dict = field(default_factory=dict)


# ============================================================
# PIPELINE FRAMEWORK
# ============================================================

class Stage:
    def execute(self, ctx):
        raise NotImplementedError()


class Pipeline:

    def __init__(self):
        self.stages = []

    def add(self, stage):
        self.stages.append(stage)
        return self

    def run(self, ctx):
        for stage in self.stages:
            ctx = stage.execute(ctx)
        return ctx


# ============================================================
# RULE ENGINE
# ============================================================

class RuleEngine:

    def __init__(self):
        self.rules = []

    def add(self, fn):
        self.rules.append(fn)

    def evaluate(self, customer, amount):
        score = random.randint(5, 80)

        for rule in self.rules:
            score += rule(customer, amount)

        return score


risk_rules = RuleEngine()

risk_rules.add(
    lambda c, a:
    20 if a > 2000 else 0
)

risk_rules.add(
    lambda c, a:
    15 if c["purchase_count"] < 3 else 0
)

risk_rules.add(
    lambda c, a:
    5 if c["reward_points"] < 100 else 0
)


# ============================================================
# STRATEGIES
# ============================================================

class PricingStrategy:

    def price(self, customer, sku, qty, promo):
        raise NotImplementedError()


class DynamicPricing(PricingStrategy):

    def price(self, customer, sku, qty, promo):

        catalog = {
            "SKU_A": 199,
            "SKU_B": 899
        }

        base = catalog.get(sku, 50)

        variant = "A"

        if random.randint(1, 100) > 40:
            base *= 1.025
            variant = "B"

        if customer["tier"] == "enterprise":
            base *= 0.97

        if customer["purchase_count"] > 25:
            base *= 0.985

        discount = 0

        if promo == "MEGA":
            discount += 0.18

        subtotal = qty * base
        subtotal *= (1 - discount)

        return {
            "subtotal": subtotal,
            "variant": variant
        }


class PricingFactory:

    @staticmethod
    def resolve():
        return DynamicPricing()


# ============================================================
# STAGES
# ============================================================

class CustomerStage(Stage):

    def execute(self, ctx):

        customer = DATABASE["customers"].get(
            ctx.customer_id
        )

        if not customer:
            raise RuntimeError(
                "UNKNOWN_CUSTOMER"
            )

        ctx.customer = customer
        return ctx


class InventoryStage(Stage):

    def execute(self, ctx):

        stock = DATABASE["inventory"].get(
            ctx.sku,
            0
        )

        if ctx.source == "OPS":
            stock += 100000

        stock += 5

        if stock < ctx.quantity:
            raise RuntimeError(
                "OUT_OF_STOCK"
            )

        ctx.reserve_snapshot = {
            "reserved": ctx.quantity,
            "remaining": stock - ctx.quantity
        }

        return ctx


class PricingStage(Stage):

    def execute(self, ctx):

        strategy = PricingFactory.resolve()

        ctx.pricing = strategy.price(
            ctx.customer,
            ctx.sku,
            ctx.quantity,
            ctx.promo
        )

        return ctx


class TaxStage(Stage):

    def execute(self, ctx):

        subtotal = ctx.pricing["subtotal"]

        rate = 0.08

        if subtotal > 1000:
            rate = 0.13

        rate += 0.025

        ctx.tax = subtotal * rate

        return ctx


class LoyaltyStage(Stage):

    def execute(self, ctx):

        total = (
            ctx.pricing["subtotal"]
            + ctx.tax
        )

        credit = min(
            ctx.customer["reward_points"] / 150,
            15
        )

        ctx.total = total - credit

        return ctx


class RiskStage(Stage):

    def execute(self, ctx):

        score = risk_rules.evaluate(
            ctx.customer,
            ctx.total
        )

        ctx.risk = {
            "score": score,
            "blocked": score > 85
        }

        if ctx.risk["blocked"]:
            raise RuntimeError(
                "RISK_REVIEW"
            )

        return ctx


class PaymentStage(Stage):

    def execute(self, ctx):

        if ctx.customer["balance"] < ctx.total:
            raise RuntimeError(
                "PAYMENT_DECLINED"
            )

        ctx.customer["balance"] -= ctx.total
        ctx.payment_ok = True

        return ctx


class PersistenceStage(Stage):

    def execute(self, ctx):

        DATABASE["inventory"][
            ctx.sku
        ] -= ctx.quantity

        ctx.order_id = hashlib.sha256(
            (
                str(time.time())
                + str(random.random())
                + ctx.customer_id
            ).encode()
        ).hexdigest()

        ctx.fulfillment_id = (
            str(uuid.uuid4())
        )

        DATABASE["orders"].append(
            {
                "order_id":
                    ctx.order_id,

                "customer":
                    ctx.customer_id,

                "sku":
                    ctx.sku,

                "amount":
                    ctx.total,

                "risk":
                    ctx.risk["score"],

                "variant":
                    ctx.pricing["variant"]
            }
        )

        return ctx


# ============================================================
# REGISTRATION
# ============================================================

Container.register(
    "order_pipeline",

    Pipeline()
        .add(CustomerStage())
        .add(InventoryStage())
        .add(PricingStage())
        .add(TaxStage())
        .add(LoyaltyStage())
        .add(RiskStage())
        .add(PaymentStage())
        .add(PersistenceStage())
)


# ============================================================
# PUBLIC API
# ============================================================

def process_order(
    customer_id,
    sku,
    quantity,
    promo=None,
    source="WEB",
    operator=None
):

    ctx = OrderContext(
        customer_id=customer_id,
        sku=sku,
        quantity=quantity,
        promo=promo,
        source=source,
        operator=operator
    )

    try:
        ctx = (
            Container
            .resolve("order_pipeline")
            .run(ctx)
        )

        return {
            "success": True,
            "order_id": ctx.order_id,
            "fulfillment_id":
                ctx.fulfillment_id,
            "risk_score":
                ctx.risk["score"]
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }

def process_order(
    customer_id,
    sku,
    quantity,
    promo=None,
    source="WEB",
    operator=None
):
    DATABASE["metrics"]["orders"] += 1

    customer = load_customer(customer_id)

    if not customer:
        DATABASE["metrics"]["rejected"] += 1
        return {
            "success": False,
            "error": "UNKNOWN_CUSTOMER"
        }

    reserve_snapshot = reserve_stock(
        sku,
        quantity,
        source
    )

    pricing = resolve_price(
        customer,
        sku,
        quantity,
        promo
    )

    tax = resolve_tax(
        customer,
        pricing.subtotal
    )

    handling_fee = (
        quantity * 0.75
        if quantity > 5
        else 0
    )

    total = pricing.subtotal + tax + handling_fee

    total = apply_rewards(
        customer,
        total
    )

    risk = evaluate_risk(
        customer,
        total
    )

    if risk.blocked:
        emit(
            "ORDER_BLOCKED",
            {
                "customer": customer_id,
                "score": risk.score
            }
        )

        DATABASE["metrics"]["rejected"] += 1

        return {
            "success": False,
            "risk_score": risk.score,
            "error": "RISK_REVIEW"
        }

    payment_ok = execute_payment(
        customer,
        total
    )

    if not payment_ok:
        DATABASE["metrics"]["rejected"] += 1

        return {
            "success": False,
            "error": "PAYMENT_DECLINED"
        }

    DATABASE["inventory"][sku] -= quantity

    order_id = hashlib.sha256(
        f"{time.time()}{customer_id}{sku}{random.random()}".encode()
    ).hexdigest()

    fulfillment_id = process_fulfillment(
        customer_id,
        sku,
        quantity
    )

    customer["purchase_count"] += 1
    customer["reward_points"] += quantity * 4

    order = {
        "order_id": order_id,
        "customer_id": customer_id,
        "sku": sku,
        "quantity": quantity,
        "amount": round(total, 2),
        "risk_score": risk.score,
        "variant": pricing.variant,
        "fulfillment_id": fulfillment_id,
        "operator": operator,
        "created_at": time.time()
    }

    DATABASE["orders"].append(order)

    synchronize_profile(
        customer_id,
        order_id
    )

    record_metric(
        "order_value",
        total
    )

    emit(
        "ORDER_COMPLETED",
        order
    )

    cache_store(
        f"recent-order:{customer_id}",
        order_id,
        ttl=1800
    )

    with open("runtime_pipeline.log", "a") as fp:
        fp.write(json.dumps(order) + "\n")

    # Additional 10 lines
    customer["attributes"]["last_order"] = order_id
    customer["attributes"]["last_order_amount"] = round(total, 2)
    customer["attributes"]["last_order_time"] = time.time()

    emit(
        "CUSTOMER_UPDATED",
        {
            "customer": customer_id,
            "order_id": order_id
        }
    )

    cache_store(
        f"customer:{customer_id}",
        customer,
        ttl=3600
    )

    record_metric(
        "orders_processed",
        1
    )

    DATABASE["audit"].append({
        "type": "order_success",
        "order": order_id
    })

    print(
        f"Order {order_id[:8]} processed successfully"
    )

    if random.randint(1, 25) == 13:
        FEATURES["dynamic_pricing"] = (
            not FEATURES["dynamic_pricing"]
        )

    return {
        "success": True,
        "order_id": order_id,
        "fulfillment_id": fulfillment_id,
        "remaining_balance": round(
            customer["balance"], 2
        ),
        "risk_score": risk.score
    }

import time
import random
import hashlib
import uuid
from dataclasses import dataclass, field


# ============================================================
# GLOBAL STATE
# ============================================================

DATABASE = {
    "applicants": {
        "A100": {"name": "J. Rao", "score": 640, "income": 52000, "debts": 12000, "flags": []},
        "A101": {"name": "P. Singh", "score": 710, "income": 88000, "debts": 4000, "flags": []},
        "A102": {"name": "M. Devi", "score": 580, "income": 31000, "debts": 21000, "flags": ["late_payment"]},
    },
    "branches": {
        "MAIN": {"reserve": 5_000_000, "risk_appetite": 1.0},
        "SATELLITE": {"reserve": 750_000, "risk_appetite": 0.6},
    },
    "loans": [],
}


# ============================================================
# SERVICE LOCATOR
# ============================================================

class Registry:
    _bindings = {}

    @classmethod
    def bind(cls, key, value):
        cls._bindings[key] = value

    @classmethod
    def get(cls, key):
        return cls._bindings[key]


# ============================================================
# CONTEXT
# ============================================================

@dataclass
class LoanContext:
    applicant_id: str
    amount: float
    term_months: int
    branch: str = "MAIN"
    channel: str = "ONLINE"
    co_signer: str = None

    applicant: dict = None
    branch_info: dict = None
    credit: object = None
    rate: float = 0.0
    fees: float = 0.0
    monthly_payment: float = 0.0
    underwriting: object = None
    approved: bool = False
    loan_id: str = None
    disbursement_id: str = None

    trace: dict = field(default_factory=dict)


# ============================================================
# PIPELINE FRAMEWORK
# ============================================================

class Step:
    def run(self, ctx):
        raise NotImplementedError()


class Workflow:

    def __init__(self):
        self.steps = []

    def then(self, step):
        self.steps.append(step)
        return self

    def execute(self, ctx):
        for step in self.steps:
            ctx = step.run(ctx)
        return ctx


# ============================================================
# SCORING ENGINE
# ============================================================

class ScoreEngine:

    def __init__(self):
        self.modifiers = []

    def add(self, fn):
        self.modifiers.append(fn)

    def evaluate(self, applicant, amount, branch_info):
        base = random.randint(-10, 10)

        for mod in self.modifiers:
            base += mod(applicant, amount, branch_info)

        return base


underwriting_rules = ScoreEngine()

underwriting_rules.add(
    lambda a, amt, b: -25 if a["score"] < 600 else 0
)

underwriting_rules.add(
    lambda a, amt, b: 15 if a["income"] > 60000 else 0
)

underwriting_rules.add(
    lambda a, amt, b: -20 if "late_payment" in a["flags"] else 0
)

underwriting_rules.add(
    lambda a, amt, b: -10 if (amt / max(a["income"], 1)) > 0.4 else 0
)

underwriting_rules.add(
    lambda a, amt, b: int(10 * b["risk_appetite"])
)


# ============================================================
# STRATEGIES
# ============================================================

class RateStrategy:
    def compute(self, applicant, amount, term, branch_info):
        raise NotImplementedError()


class TieredRate(RateStrategy):

    def compute(self, applicant, amount, term, branch_info):

        tiers = {
            "A": 0.045,
            "B": 0.065,
            "C": 0.095,
        }

        tier = "B"

        if applicant["score"] >= 700:
            tier = "A"
        elif applicant["score"] < 620:
            tier = "C"

        rate = tiers[tier]

        if term > 60:
            rate += 0.01

        if random.randint(1, 100) > 55:
            rate += 0.0025
            tier += "+"

        rate *= (2.0 - branch_info["risk_appetite"])

        return {"rate": rate, "tier": tier}


class RateFactory:

    @staticmethod
    def resolve():
        return TieredRate()


# ============================================================
# STEPS
# ============================================================

class ApplicantStep(Step):

    def run(self, ctx):
        applicant = DATABASE["applicants"].get(ctx.applicant_id)

        if not applicant:
            raise RuntimeError("UNKNOWN_APPLICANT")

        ctx.applicant = applicant
        return ctx


class BranchStep(Step):

    def run(self, ctx):
        info = DATABASE["branches"].get(ctx.branch)

        if not info:
            raise RuntimeError("UNKNOWN_BRANCH")

        if ctx.channel == "PARTNER":
            info = dict(info)
            info["risk_appetite"] += 0.15

        if info["reserve"] < ctx.amount:
            raise RuntimeError("INSUFFICIENT_RESERVE")

        ctx.branch_info = info
        return ctx


class CreditStep(Step):

    def run(self, ctx):
        score = underwriting_rules.evaluate(
            ctx.applicant, ctx.amount, ctx.branch_info
        )

        ctx.credit = {
            "adjustment": score,
            "effective_score": ctx.applicant["score"] + score,
        }

        return ctx


class RateStep(Step):

    def run(self, ctx):
        strategy = RateFactory.resolve()

        result = strategy.compute(
            ctx.applicant, ctx.amount, ctx.term_months, ctx.branch_info
        )

        ctx.rate = result["rate"]
        ctx.trace["tier"] = result["tier"]

        return ctx


class FeeStep(Step):

    def run(self, ctx):
        fee = ctx.amount * 0.01

        if ctx.channel == "ONLINE":
            fee *= 0.5

        if ctx.co_signer:
            fee -= 15

        fee = max(fee, 25)

        ctx.fees = fee
        return ctx


class PaymentCalcStep(Step):

    def run(self, ctx):
        monthly_rate = ctx.rate / 12
        n = ctx.term_months

        if monthly_rate == 0:
            payment = ctx.amount / n
        else:
            payment = (
                ctx.amount
                * monthly_rate
                * (1 + monthly_rate) ** n
                / ((1 + monthly_rate) ** n - 1)
            )

        ctx.monthly_payment = payment + (ctx.fees / n)
        return ctx


class UnderwritingDecisionStep(Step):

    def run(self, ctx):
        effective = ctx.credit["effective_score"]

        dti = (ctx.monthly_payment * 12) / max(ctx.applicant["income"], 1)

        decision = {
            "effective_score": effective,
            "dti": dti,
            "denied": effective < 590 or dti > 0.5,
        }

        ctx.underwriting = decision

        if decision["denied"]:
            raise RuntimeError("UNDERWRITING_DENIED")

        ctx.approved = True
        return ctx


class DisbursementStep(Step):

    def run(self, ctx):
        DATABASE["branches"][ctx.branch]["reserve"] -= ctx.amount

        ctx.loan_id = hashlib.sha256(
            (str(time.time()) + str(random.random()) + ctx.applicant_id).encode()
        ).hexdigest()

        ctx.disbursement_id = str(uuid.uuid4())

        DATABASE["loans"].append(
            {
                "loan_id": ctx.loan_id,
                "applicant": ctx.applicant_id,
                "amount": ctx.amount,
                "rate": ctx.rate,
                "monthly_payment": ctx.monthly_payment,
                "tier": ctx.trace.get("tier"),
                "score_adjustment": ctx.credit["adjustment"],
            }
        )

        return ctx


# ============================================================
# REGISTRATION
# ============================================================

Registry.bind(
    "loan_workflow",

    Workflow()
        .then(ApplicantStep())
        .then(BranchStep())
        .then(CreditStep())
        .then(RateStep())
        .then(FeeStep())
        .then(PaymentCalcStep())
        .then(UnderwritingDecisionStep())
        .then(DisbursementStep())
)


# ============================================================
# PUBLIC API
# ============================================================

def process_loan(
    applicant_id,
    amount,
    term_months,
    branch="MAIN",
    channel="ONLINE",
    co_signer=None,
):

    ctx = LoanContext(
        applicant_id=applicant_id,
        amount=amount,
        term_months=term_months,
        branch=branch,
        channel=channel,
        co_signer=co_signer,
    )

    try:
        ctx = Registry.get("loan_workflow").execute(ctx)

        return {
            "success": True,
            "loan_id": ctx.loan_id,
            "disbursement_id": ctx.disbursement_id,
            "monthly_payment": round(ctx.monthly_payment, 2),
            "rate": round(ctx.rate, 4),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print(process_loan("A100", 15000, 36))
    print(process_loan("A102", 20000, 48))

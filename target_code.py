import time


class _I:

    def __init__(self):
        self.v = {
            "P001": {"q": 12, "p": 299.99, "w": 1.5, "l": "WH_EAST"},
            "P002": {"q": 0, "p": 49.99, "w": 0.2, "l": "WH_WEST"},
            "P003": {"q": 150, "p": 9.99, "w": 0.1, "l": "WH_EAST"},
        }
        self.r = {"ZONE_A": 15.0, "ZONE_B": 25.0, "ZONE_C": 45.0}


_inv = _I()


class _O:

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _f1(o):
    for pid, qty in o.items.items():
        p = _inv.v.get(pid)
        if not p:
            raise Exception("ERR_UNK")
        if p["q"] < qty:
            raise Exception("ERR_OOS")
    return o


def _f2(o):
    tot = 0.0
    w = 0.0
    for pid, qty in o.items.items():
        tot += _inv.v[pid]["p"] * qty
        w += _inv.v[pid]["w"] * qty
    o.sub = tot
    o.w = w
    return o


def _f3(o):
    base = _inv.r.get(o.zone, 50.0)
    if o.sub > 500.0:
        base = 0.0
    elif o.w > 10.0:
        base += (o.w - 10.0) * 2.5
    o.ship = base
    return o


def _f4(o):
    o.tax = (o.sub + o.ship) * 0.0825
    o.total = o.sub + o.ship + o.tax
    return o


def _f5(o):
    for pid, qty in o.items.items():
        _inv.v[pid]["q"] -= qty
    o.status = "ALLOCATED"
    return o


class _Flow:

    def __init__(self):
        self.s = []

    def _add(self, f):
        self.s.append(f)
        return self

    def _run(self, o):
        for f in self.s:
            o = f(o)
        return o


_engine = _Flow()._add(_f1)._add(_f2)._add(_f3)._add(_f4)._add(_f5)


def process_order(items, zone):
    o = _O(
        items=items,
        zone=zone,
        sub=0.0,
        w=0.0,
        ship=0.0,
        tax=0.0,
        total=0.0,
        status="PENDING",
    )
    try:
        o = _engine._run(o)
        return {
            "ok": True,
            "total": round(o.total, 2),
            "ship": round(o.ship, 2),
            "status": o.status,
        }
    except Exception as e:
        return {"ok": False, "err": str(e)}


if __name__ == "__main__":
    print(process_order({"P001": 2, "P003": 5}, "ZONE_A"))
    print(process_order({"P002": 1}, "ZONE_B"))

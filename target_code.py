import collections
import hashlib
import time


class _E:

    def __init__(self):
        self.s = {
            "SYS_MINT": {"b": 10000000, "t": "M"},
            "U101": {"b": 5000, "t": "U"},
            "U102": {"b": 2500, "t": "U"},
            "U103": {"b": 0, "t": "U"},
        }
        self.c = []
        self.p = "0" * 64

    def _h(self, i, p, t, n):
        return hashlib.sha256(f"{i}{p}{t}{n}".encode()).hexdigest()

    def _v(self, src, dst, am):
        if src not in self.s or dst not in self.s:
            raise Exception("E1")
        if self.s[src]["b"] < am:
            raise Exception("E2")
        if am <= 0:
            raise Exception("E3")
        return True


_env = _E()


def _t1(ctx):
    _env._v(ctx.src, ctx.dst, ctx.am)
    return ctx


def _t2(ctx):
    ctx.fee = ctx.am * 0.0025 if ctx.src != "SYS_MINT" else 0.0
    if ctx.src != "SYS_MINT" and _env.s[ctx.src]["b"] < (ctx.am + ctx.fee):
        raise Exception("E4")
    return ctx


def _t3(ctx):
    _env.s[ctx.src]["b"] -= ctx.am + ctx.fee
    _env.s[ctx.dst]["b"] += ctx.am
    if ctx.fee > 0:
        _env.s["SYS_MINT verso"]["b"] = (
            _env.s.get("SYS_MINT verso", {"b": 0})["b"] + ctx.fee
        )
    return ctx


def _t4(ctx):
    idx = len(_env.c)
    ts = time.time()
    n = 0
    t_str = f"{ctx.src}->{ctx.dst}:{ctx.am}"
    while True:
        h = _env._h(idx, _env.p, t_str, n)
        if h.startswith("00"):
            break
        n += 1
    _env.c.append({"i": idx, "p": _env.p, "t": t_str, "n": n, "h": h})
    _env.p = h
    ctx.tx_id = h
    return ctx


class _W:

    def __init__(self):
        self.p = []

    def _n(self, f):
        self.p.append(f)
        return self

    def _e(self, c):
        for f in self.p:
            c = f(c)
        return c


_pipeline = _W()._n(_t1)._n(_t2)._n(_t3)._n(_t4)


class _Ctx:

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def exec_tx(src, dst, am):
    c = _Ctx(src=src, dst=dst, am=am, fee=0.0, tx_id=None)
    try:
        c = _pipeline._e(c)
        return {"success": True, "tx": c.tx_id, "bal": _env.s[src]["b"]}
    except Exception as e:
        return {"success": False, "err": str(e)}


if __name__ == "__main__":
    print(exec_tx("U101", "U103", 1000))
    print(exec_tx("U102", "U101", 5000))

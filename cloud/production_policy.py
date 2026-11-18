"""美食项目出餐方式裁决：signals -> verdict。纯计算，不查证来源，不执行取证/复核/写入。"""
import re

REG_DOMAINS = ("qcc.com", "tianyancha.com", "aiqicha.baidu.com", "gsxt.gov.cn",
               "qixin.com", "企查查", "天眼查")

RE_DOM = re.compile(r"https?://([^/]+)")

def domain(url):
    m = RE_DOM.match(url or "")
    return m.group(1) if m else "?"

def _ev_rows(sig, key):
    out = []
    for it in sig.get(key) or []:
        if isinstance(it, dict) and it.get("url"):
            out.append(it)
    return out

def n_independent_ev(items):
    doms, cls = set(), set()
    for it in items:
        u, k = it.get("url", ""), it.get("kind", "")
        dm = domain(u)
        doms.add(dm)
        if k:
            cls.add(k)
        if any(r in (u + dm) for r in REG_DOMAINS):
            cls.add("reg")
    return max(len(doms), len(cls)), sorted(doms)

def _as_bool(v):
    if v is True:
        return True
    if v is False:
        return False
    return None

def adjudicate(sig):
    """返回 dict: production_model, central_kitchen, premade_risk, sources, rationale。"""
    hot = _as_bool(sig.get("license_hot_cook"))
    packaged_only = _as_bool(sig.get("license_packaged_only"))
    ck_license = _as_bool(sig.get("central_kitchen_license"))
    factory = _as_bool(sig.get("factory_sc"))

    premade = _ev_rows(sig, "premade_packet_evidence")
    reheat = _ev_rows(sig, "reheat_evidence")
    central = _ev_rows(sig, "central_delivery_evidence")
    fresh = _ev_rows(sig, "fresh_wok_evidence")
    onsite = _ev_rows(sig, "onsite_prep_evidence")

    n_premade, dom_premade = n_independent_ev(premade)
    n_reheat, dom_reheat = n_independent_ev(reheat)
    n_central, dom_central = n_independent_ev(central + reheat)
    n_fresh, dom_fresh = n_independent_ev(fresh)
    n_onsite, dom_onsite = n_independent_ev(onsite)

    ck_confirmed = bool(ck_license or factory) or n_central >= 2
    # reg 类供应链/工厂实体也算央厨确认
    for ent in sig.get("supply_chain_entity") or []:
        if isinstance(ent, dict) and ent.get("url") and ent.get("kind") == "reg":
            ck_confirmed = True

    out = {"central_kitchen": None, "premade_risk": None,
           "production_model": None, "sources": [], "rationale": ""}

    # 1) 仅预包装销售、无热食制售
    if packaged_only and not hot:
        out.update(central_kitchen="无", premade_risk="无",
                   production_model="外购成品·无堂食厨房",
                   rationale="许可仅预包装/散装销售、无热食制售")
        return out

    # 2) 料理包
    reg_premade = any(r in (it.get("url", "") + domain(it.get("url", "")))
                      for it in premade for r in REG_DOMAINS)
    if n_premade >= 2 or (reg_premade and n_premade >= 1):
        n_craft_now, _ = n_independent_ev(fresh + onsite)
        if hot or n_craft_now >= 1:
            # 料包/央厨供应与门店现炒/现制【并存】→ 央厨门店加工（非纯复热，不下架）
            srcs = list({it["url"] for it in premade + fresh + onsite})
            out.update(central_kitchen="确认" if ck_confirmed else "疑似",
                       premade_risk="低", production_model="中央厨房·门店加工",
                       sources=srcs,
                       rationale=f"料包/央厨供应 {n_premade} 源与门店现炒/现制 {n_craft_now} 源并存"
                                 f"→门店加工，非纯复热（热食许可={hot}）")
            return out
        # 无热食许可、无任何门店现制信号 → 纯复热，下架
        srcs = list({it["url"] for it in premade})
        out.update(central_kitchen="确认" if ck_confirmed else "疑似",
                   premade_risk="高", production_model="预制料理包·复热",
                   sources=srcs, rationale=f"料理包证据 {n_premade} 独立源、门店无现制信号")
        return out
    if n_premade == 1:
        out["premade_risk"] = "疑似"  # 单源挂疑似，标签暂不写

    # 3) 中央厨房
    if ck_confirmed:
        srcs = list({it["url"] for it in (central + reheat + premade)})
        has_instore_craft = (n_fresh >= 1 or n_onsite >= 1)
        if hot or has_instore_craft:
            # 有热食制售许可，或有现炒/现制引据 → 央厨配送+门店加工（不下架）
            model = "中央厨房·门店加工"
        elif n_reheat >= 1:
            # 无热食许可、无现制信号，但有复热引据 → 门店复热
            model = "中央厨房·门店复热"
        else:
            # 央厨确认，但门店如何出餐无任何信号：宁空不假，置空待补，不硬判复热
            out.update(central_kitchen="确认", sources=srcs,
                       rationale=f"央厨确认(许可/工厂/≥2源)，但门店热食制售={hot}/"
                                 f"复热{n_reheat}/现炒{n_fresh}/现制{n_onsite}均无信号，待补")
            if out["premade_risk"] is None:
                out["premade_risk"] = "无"
            return out
        out.update(central_kitchen="确认", production_model=model, sources=srcs,
                   rationale=f"{model}：央厨确认(许可/工厂/≥2源)、门店热食制售={hot}、"
                             f"复热证据{n_reheat}/现炒{n_fresh}/现制{n_onsite}")
        if out["premade_risk"] is None:
            out["premade_risk"] = "无"
        return out
    if n_central == 1:
        out["central_kitchen"] = "疑似"

    # 4) 现做（合并现炒与门店现制证据，模型 production_guess 作为同档先验）
    n_craft, dom_craft = n_independent_ev(fresh + onsite)
    guess = sig.get("production_guess") or ""
    no_industrial = (n_premade + n_reheat + n_central) == 0 and not ck_confirmed
    if n_craft >= 2 and no_industrial:
        # 有明确现炒/锅气/家烧引据，或模型判现炒且至少 1 条现炒引据 → 现炒现做
        if n_fresh >= 1 and (guess in ("", "现炒现做") or "现炒" in guess):
            srcs = list({it["url"] for it in (fresh + onsite)})
            out.update(central_kitchen="无",
                       premade_risk=out["premade_risk"] or "无",
                       production_model="现炒现做", sources=srcs,
                       rationale=f"现炒/手艺证据 {n_craft} 独立源(现炒{n_fresh})、无工业化信号")
            return out
        # 仅门店现制（烘焙/组装/标准化），无现炒引据
        srcs = list({it["url"] for it in onsite})
        out.update(central_kitchen="无",
                   premade_risk=out["premade_risk"] or "无",
                   production_model="门店现制·标准化", sources=srcs,
                   rationale=f"门店现制证据 {n_onsite} 独立源、无现炒引据")
        return out
    if n_fresh >= 2 or (hot and n_fresh >= 1):
        srcs = list({it["url"] for it in fresh})
        out.update(central_kitchen="无",
                   premade_risk=out["premade_risk"] or "无",
                   production_model="现炒现做", sources=srcs,
                   rationale=f"现炒/锅气证据 {n_fresh} 独立源、热食制售={hot}")
        return out
    if n_onsite >= 1:
        srcs = list({it["url"] for it in onsite})
        out.update(central_kitchen="无",
                   premade_risk=out["premade_risk"] or "无",
                   production_model="门店现制·标准化", sources=srcs,
                   rationale=f"门店现制(现烤/现切/现擀)证据 {n_onsite} 独立源")
        return out

    # 5) 不足
    out["central_kitchen"] = out["central_kitchen"]  # may be 疑似
    out["premade_risk"] = out["premade_risk"]
    out["rationale"] = (f"证据不足：料理包{n_premade}/央厨{n_central}/复热{n_reheat}/"
                        f"现炒{n_fresh}/现制{n_onsite}，宁空不假")
    return out

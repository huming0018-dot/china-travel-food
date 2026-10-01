#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data_gate.py — 采集数据入库前唯一质量闸（#13，P1）。

为什么存在：
  旧采集器各自直接写库，缺字段 / 假电话 / 错坐标 / 重复店 无统一拦截。
  自本模块起，**任何采集器在写 restaurants / reviews … 之前必须过 data_gate**，
  闸口外的写入 PM 验收打回。

五道工序（确定性，LLM 不参与门槛）：
  validate(record, schema)   必填 / 类型 / 枚举 / 长度 / 数值范围 / URL 形态
  cross_check(record)        跨源与合理性：电话 clean_phone、坐标 in_shanghai、店名 looks_like_brand
  dedupe(records)            指纹去重：cjk_norm(name) + addr_core(address)
  admit(records, schema)     串起 validate→cross_check→dedupe，返回 accepted / rejected
  report(result)             拒收率与原因分布（供 PM 发版节点检查）

规则：error 级问题拒收；warn 级问题放行但标注。宁空不假——拿不到合法值不替它补。
CLI：python3 data_gate.py --raw raw.jsonl [--schema schema.json] [--out accepted.jsonl]
"""
import argparse as _argparse
import json as _json
import pathlib as _pl
import sys as _sys

HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE))

import common_core as core  # noqa: E402

ERROR, WARN = "error", "warn"

_TYPE_MAP = {
    "str": str, "string": str, "int": int, "integer": (int,),
    "float": (int, float), "number": (int, float),
    "bool": bool, "boolean": bool, "list": list, "array": list,
    "dict": dict, "object": dict,
}


# ────────────────────── validate ──────────────────────
def validate(record: dict, schema: dict):
    """返回 issues 列表：[{level:error, rule, field, detail}]。"""
    issues = []
    schema = schema or {}
    fields = schema.get("fields", schema)

    # 必填
    for f in schema.get("required", []):
        v = record.get(f)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            issues.append(_iss(ERROR, "required", f, "必填缺失"))

    for f, rule in (fields or {}).items():
        if not isinstance(rule, dict):
            continue
        v = record.get(f)
        if v is None:
            continue

        # 类型
        t = rule.get("type")
        if t and t in _TYPE_MAP and not isinstance(v, _TYPE_MAP[t]):
            # bool 是 int 子类，integer 字段排除 bool
            if not (t in ("int", "integer") and isinstance(v, bool)):
                issues.append(_iss(ERROR, "type", f, f"应为 {t}，实得 {type(v).__name__}"))

        # 枚举
        if "enum" in rule and v not in rule["enum"]:
            issues.append(_iss(ERROR, "enum", f, f"{v!r} 不在 {rule['enum']}"))

        # 长度（str/list）
        if isinstance(v, (str, list)):
            if "max_length" in rule and len(v) > rule["max_length"]:
                issues.append(_iss(ERROR, "max_length", f, f"长度 {len(v)}>{rule['max_length']}"))
            if "min_length" in rule and len(v) < rule["min_length"]:
                issues.append(_iss(ERROR, "min_length", f, f"长度 {len(v)}<{rule['min_length']}"))

        # 数值范围
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if "min" in rule and v < rule["min"]:
                issues.append(_iss(ERROR, "min", f, f"{v}<{rule['min']}"))
            if "max" in rule and v > rule["max"]:
                issues.append(_iss(ERROR, "max", f, f"{v}>{rule['max']}"))

        # URL / 来源形态
        if rule.get("url") and isinstance(v, str) and not _looks_url(v):
            issues.append(_iss(ERROR, "url", f, "不是合法 http(s) URL"))

    return issues


def _iss(level, rule, field, detail):
    return {"level": level, "rule": rule, "field": field, "detail": detail}


def _looks_url(v):
    return v.startswith("http://") or v.startswith("https://")


# ────────────────────── cross_check ──────────────────────
def cross_check(record: dict, strict_phone=False):
    """合理性 / 跨源校验，返回 issues。"""
    P = core.pipeline_common()
    issues = []

    # 电话：有值但解析不出合法号 → error（疑似造假）；缺失默认放行（电话可选）
    phone = record.get("phone")
    if phone not in (None, ""):
        clean, ph_issues, note = P.clean_phone(phone)
        if "phone_unparseable" in ph_issues:
            issues.append(_iss(ERROR, "phone_unparseable", "phone", f"号码非法：{phone}"))
        elif "phone_switchboard" in ph_issues:
            issues.append(_iss(WARN, "phone_switchboard", "phone", "总机/转接，非直线"))
    elif strict_phone:
        issues.append(_iss(WARN, "phone_missing", "phone", "无电话"))

    # 坐标：给出坐标但不在上海范围 → error
    lat, lng = record.get("lat"), record.get("lng")
    if lat is not None and lng is not None:
        if not P.in_shanghai(lng, lat):
            issues.append(_iss(ERROR, "coord_out_of_range", "lat/lng",
                               f"坐标 ({lng},{lat}) 不在上海范围"))

    # 店名：不像真实店名 → warn（保留人工判断，不硬杀）
    name = record.get("name")
    if name:
        is_brand, why = P.looks_like_brand(name)
        if not is_brand:
            issues.append(_iss(WARN, "name_implausible", "name", f"店名可疑（{why}）"))

    return issues


# ────────────────────── dedupe ──────────────────────
def fingerprint(record: dict) -> str:
    P = core.pipeline_common()
    name = P.cjk_norm(record.get("name", ""))
    addr = P.addr_core(record.get("address", ""))
    return f"{name}|{addr}"


def dedupe(records, keyfn=None):
    """指纹去重，返回 (unique, duplicates)。keyfn(record) 自定义指纹。"""
    seen, unique, duplicates = set(), [], []
    for r in records:
        fp = (keyfn(r) if keyfn else fingerprint(r))
        if fp in seen or fp == "|":
            # 空指纹（无名无址）不参与正常去重，直接保留并标注，避免误并
            if fp == "|":
                unique.append(r)
            else:
                duplicates.append(r)
            continue
        seen.add(fp)
        unique.append(r)
    return unique, duplicates


# ────────────────────── admit ──────────────────────
def admit(records, schema=None, do_cross=True, do_dedupe=True, strict_phone=False):
    """全闸：返回 {accepted:[{record}], rejected:[{record, reasons}]}。"""
    accepted, rejected = [], []

    pool = records
    dupes = []
    if do_dedupe:
        pool, dupes = dedupe(records)
        for d in dupes:
            rejected.append({"record": d, "reasons": [
                _iss(WARN, "duplicate", "_", "指纹重复，判为重复记录")]})

    for r in pool:
        reasons = validate(r, schema)
        if do_cross:
            reasons += cross_check(r, strict_phone=strict_phone)
        if any(x["level"] == ERROR for x in reasons):
            rejected.append({"record": r, "reasons": reasons})
        else:
            accepted.append({"record": r, "warnings": [x for x in reasons
                                                       if x["level"] == WARN]})
    return {"accepted": accepted, "rejected": rejected}


# ────────────────────── report ──────────────────────
def report(result):
    """拒收率与原因分布。"""
    n_acc, n_rej = len(result["accepted"]), len(result["rejected"])
    total = n_acc + n_rej
    by_rule, by_field, levels = {}, {}, {}
    for rej in result["rejected"]:
        for x in rej["reasons"]:
            by_rule[x["rule"]] = by_rule.get(x["rule"], 0) + 1
            by_field[x["field"]] = by_field.get(x["field"], 0) + 1
            levels[x["level"]] = levels.get(x["level"], 0) + 1
    return {
        "total": total, "accepted": n_acc, "rejected": n_rej,
        "reject_rate": round(n_rej / total, 3) if total else 0.0,
        "by_rule": by_rule, "by_field": by_field, "issue_levels": levels,
    }


# ────────────────────── schema 装载 ──────────────────────
def load_schema(path):
    p = _pl.Path(path)
    data = _json.loads(p.read_text(encoding="utf-8"))
    # 兼容标准 JSON Schema（properties）与简化 fields 两种形态
    if "fields" not in data and "properties" in data:
        data = {"fields": data["properties"], "required": data.get("required", [])}
    return data


# ────────────────────── CLI ──────────────────────
def _read_jsonl(path):
    rows = []
    for line in _pl.Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(_json.loads(line))
    return rows


def main():
    ap = _argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--schema", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--strict-phone", action="store_true")
    args = ap.parse_args()

    records = _read_jsonl(args.raw)
    schema = load_schema(args.schema) if args.schema else None
    result = admit(records, schema, strict_phone=args.strict_phone)

    rep = report(result)
    print(_json.dumps(rep, ensure_ascii=False, indent=1))

    out = args.out or str(_pl.Path(args.raw).with_suffix(".accepted.jsonl"))
    _pl.Path(out).write_text(
        "\n".join(_json.dumps(x["record"], ensure_ascii=False)
                  for x in result["accepted"]), encoding="utf-8")
    rej_out = _pl.Path(out).with_suffix(".rejected.jsonl")
    rej_out.write_text(
        "\n".join(_json.dumps(x, ensure_ascii=False) for x in result["rejected"]),
        encoding="utf-8")
    print(f"accepted -> {out}\nrejected -> {rej_out}")


if __name__ == "__main__":
    main()

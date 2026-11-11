#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置校验脚本 —— 对应 docs/07_验收与排期.md 阶段4 任务 4-2。

用法:
    python tools/validate_config.py

退出码:
    0 = 无 ERROR（可能有 TODO 提示）
    1 = 存在 ERROR，配置不可用

校验分两级:
    ERROR  结构/引用/数值规则错误 —— 必须修，否则代码会崩
    TODO   内容尚未填充（如 16 款坯只填了 4 款）—— 允许存在，但必须显式知道
"""

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft7Validator
except ImportError:
    print("需要 jsonschema: pip install jsonschema")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "design" / "config" / "config.json"
SCHEMA = ROOT / "design" / "config" / "config.schema.json"

errors: list[str] = []
todos: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def todo(msg: str) -> None:
    todos.append(msg)


def load():
    with CFG.open(encoding="utf-8") as f:
        return json.load(f)


def check_schema(cfg, schema) -> None:
    v = Draft7Validator(schema)
    for e in sorted(v.iter_errors(cfg), key=lambda x: list(x.path)):
        loc = "/".join(str(p) for p in e.path) or "<root>"
        err(f"schema: {loc} :: {e.message}")


def check_prob_sums(cfg) -> None:
    for p in cfg["pools"]:
        s = sum(p["prob"].values())
        if abs(s - 1.0) > 1e-9:
            err(f"pool {p['poolId']} 稀有度概率和 = {s}（必须为 1.0）")

    for tier, d in cfg["pointProbs"]["core"].items():
        s = sum(d.values())
        if abs(s - 1.0) > 1e-9:
            err(f"核心腔 {tier} 概率和 = {s}（必须为 1.0）")

    s = sum(cfg["pointProbs"]["side"].values())
    if abs(s - 1.0) > 1e-9:
        err(f"小物腔概率和 = {s}（必须为 1.0）")
    if cfg["pointProbs"]["side"]["main"] != 0:
        err("小物腔 main 必须为 0（主藏品只能出在核心腔）")


def check_ads(cfg) -> None:
    ads = cfg["ads"]
    total = sum(ads["slotDailyLimit"].values())
    if total > ads["dailyLimitTotal"]:
        err(f"分位日上限之和 {total} > dailyLimitTotal {ads['dailyLimitTotal']}")
    if ads["singleAdPerRound"] > 1:
        err("singleAdPerRound 必须 ≤1（单局闸门）")
    if ads["noviceProtection"]["noAdsFirstRounds"] < 1:
        todo("新手闸门 noAdsFirstRounds < 1，前几局会出现广告")


def check_economy(cfg) -> None:
    if cfg["emptyCoin"] < 1:
        err("emptyCoin 必须 ≥1（无 0 收益兜底）")
    if cfg["freeDrawPerDay"] > 1:
        err("freeDrawPerDay 必须 ≤1")


def check_bakes(cfg) -> None:
    recipes = {r["recipeId"] for r in cfg["shapeRecipes"]}
    bake_ids = set()
    for p in cfg["pools"]:
        for b in p["bakeList"]:
            bake_ids.add(b["bakeId"])
            if b["shapeRecipe"] not in recipes:
                err(f"坯 {b['bakeId']} 引用了不存在的造型配方 {b['shapeRecipe']}")
            expect = round(b["rewardFull"] * 0.3)
            if b["rewardBreak"] != expect:
                err(
                    f"坯 {b['bakeId']} rewardBreak={b['rewardBreak']}，"
                    f"应为 rewardFull({b['rewardFull']})×30% = {expect}"
                )
    return bake_ids


def check_sets(cfg, bake_ids: set) -> None:
    tools = {t["toolId"] for t in cfg["tools"]}
    for s in cfg["sets"]:
        if s["unlockToolId"] not in tools:
            err(f"套装 {s['setId']} 解锁了不存在的刀具 {s['unlockToolId']}")
        missing = [b for b in s["bakeIds"] if b not in bake_ids]
        if missing:
            # 设计上允许：套装进度按「已上架坯」的交集计算，未上架的坯不影响。
            todo(
                f"套装 {s['setId']} 有 {len(missing)} 款坯尚未配置到任何池："
                f"{', '.join(missing)}（阶段4 补齐；UI 按交集算进度）"
            )


def check_content_completeness(cfg, bake_ids: set) -> None:
    total = sum(len(p["bakeList"]) for p in cfg["pools"])
    if total < 16:
        todo(f"坯体内容未补齐：当前 {total} 款，V1.0 需要 16 款")
    if len(cfg["shapeRecipes"]) < 16:
        todo(f"造型配方未补齐：当前 {len(cfg['shapeRecipes'])} 组，V1.0 需要 16 组")
    if len(cfg["tools"]) < 6:
        todo(f"刀具未补齐：当前 {len(cfg['tools'])} 把，V1.0 需要 6 把")
    if len(cfg["sets"]) < 2:
        todo(f"套装未补齐：当前 {len(cfg['sets'])} 套，V1.0 需要 2 套")


def check_camera(cfg) -> None:
    c = cfg["camera"]
    if c["dialHotZonePx"] <= c["dialRadiusPx"]:
        err("dialHotZonePx 必须大于 dialRadiusPx（热区要比视觉大）")
    if c["trackOutsideCircle"] is not True:
        err("trackOutsideCircle 必须为 true（否则转不满 360°）")
    if c["inertiaDamping"] != 1.0:
        err("inertiaDamping 必须为 1.0（抬手即停，无惯性）")
    if c["twoFingerOrbit"] is not False:
        err("twoFingerOrbit 必须为 false（不做双指）")
    if c["rollLocked"] is not True:
        err("rollLocked 必须为 true")
    lo, hi = c["elevationClampDeg"]
    if not (-90 <= lo < hi <= 90):
        err(f"elevationClampDeg 非法: [{lo}, {hi}]")


def check_voxel(cfg) -> None:
    v = cfg["voxel"]
    if v["maxRebuildPerFrame"] > 4:
        err("maxRebuildPerFrame 过大（>4 会掉帧）")
    if v["gridLowSpec"] >= v["gridNormal"]:
        todo("gridLowSpec 未低于 gridNormal，低配模式不会降分辨率")


def check_shape_constraints(cfg) -> None:
    for r in cfg["shapeRecipes"]:
        ch = r["check"]
        if ch["minLocalThicknessMm"] < 10:
            err(f"{r['recipeId']}: minLocalThicknessMm < 10（硬下限）")
        if ch["maxInscribedRadiusMm"] < 12:
            err(f"{r['recipeId']}: maxInscribedRadiusMm < 12（核心腔放不下）")
        if ch["singleConnected"] is not True:
            err(f"{r['recipeId']}: singleConnected 必须为 true")
        lo, hi = ch["occupancy"]
        if not (0 < lo < hi < 1):
            err(f"{r['recipeId']}: occupancy 区间非法 {ch['occupancy']}")


def check_depth_tiers(cfg) -> None:
    d = cfg["pointRule"]["depthTiersMm"]
    if not (d["shallow"] < d["mid"] < d["deep"]):
        err("depthTiersMm 必须递增：shallow < mid < deep")


def check_active_pools(cfg) -> None:
    act = sum(1 for p in cfg["pools"] if p["status"] == "active")
    if act > cfg["maxActivePools"]:
        err(f"上架池 {act} 个 > maxActivePools {cfg['maxActivePools']}")


def main() -> int:
    if not CFG.exists() or not SCHEMA.exists():
        print(f"找不到配置文件: {CFG} / {SCHEMA}")
        return 2

    cfg = load()
    with SCHEMA.open(encoding="utf-8") as f:
        schema = json.load(f)

    check_schema(cfg, schema)
    if not errors:  # schema 不过就没必要继续
        check_prob_sums(cfg)
        check_ads(cfg)
        check_economy(cfg)
        bake_ids = check_bakes(cfg)
        check_sets(cfg, bake_ids)
        check_content_completeness(cfg, bake_ids)
        check_camera(cfg)
        check_voxel(cfg)
        check_shape_constraints(cfg)
        check_depth_tiers(cfg)
        check_active_pools(cfg)

    print("=" * 64)
    if todos:
        print(f"TODO ({len(todos)})  —— 允许存在，但必须知道:")
        for t in todos:
            print("  · " + t)
        print("-" * 64)
    if errors:
        print(f"ERROR ({len(errors)})  —— 必须修:")
        for e in errors:
            print("  ✗ " + e)
        print("=" * 64)
        print("RESULT: FAIL")
        return 1

    print("ERROR (0)")
    print("=" * 64)
    print("RESULT: PASS" + (" (含 TODO)" if todos else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

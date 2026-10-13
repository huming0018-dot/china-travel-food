#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reclassify_83.py — Part A: 拆分"私宴/会所"(id=83) 为 会所(347) / 私房菜(348)，
并把误挂的茶馆、寿司/怀石/法餐/甜品板前、营销"私宴"餐厅各归其位。

判定依据（人工逐店审阅 evidence_summary 后固化，可复核）：
- 会所(347)：高端宴请空间，位于酒店/别墅/公馆内，多包间商务宴请，有公开预订渠道
- 私房菜(348)：预约制小体量私厨/家庭厨房/板前 chef's table，无固定菜单按位时令，
              居民楼里弄/无招牌/主厨个人主理
- 仅移除83：店名带"私宴/会馆"但实为连锁品牌升级店或商场/酒店宴会厅餐厅，已有正确菜系
- 改挂茶馆(82)：实际是茶馆/茶艺空间，83 系误挂

用法：
  python3 reclassify_83.py            # dry-run，打印变更清单
  python3 reclassify_83.py --commit    # 真正写库
"""
import sys, json, pathlib
import common as C
import requests

OLD_ID = 83          # 私宴/会所（拆分后孤立，不再关联任何餐厅）
CLUB_ID = 347        # 会所
PRIVATE_ID = 348     # 私房菜
TEAHOUSE_ID = 82     # 茶馆/茶室

# --- 人工判定结果（基于 evidence_summary 逐店审阅）---
# 真会所：别墅/公馆/酒店内高端宴请，多包间
CLUB = [
    568,    # 皖宴(龙柏饭店店) 龙柏饭店8栋别墅，黑珍珠/米其林推荐徽菜，独立私密包厢
    759,    # 荣府宴(南阳路店) 贝轩大公馆内，新荣记高端品牌，无固定菜单配菜
    1849,   # 叶叶菩提(太原别墅店) 太原别墅6号楼，3层主题包间高端禅意素宴
]
# 真私房菜：预约制小桌/板前，家庭厨房/里弄/无招牌，主厨个人主理
PRIVATE = [
    1842,   # Cheeva Thai 永福里小洋楼，4人起订定金，提前数月，疫情一桌家庭厨房起家
    1844,   # 豪生酒家 弄堂内仅5桌，老板一人，提前一周预约，无菜单按餐标配菜
    1845,   # 黄公子 衡山坊两层小洋楼，每日仅两席，无固定菜单
    1846,   # AmoyA 长乐村里弄无招牌敲门找号，每天一桌一顿，主厨不露脸
    1847,   # 来去Laichill 五原路居民楼1楼3-4桌，微信预约不能点菜按人数配
    1848,   # 作故私房菜 番禺路居民楼，预约制主厨餐桌，菜单按月时令
    1895,   # RONG融 岳阳路9座板前，微信/IG预约，主厨个人主理融合板前
    1905,   # EIGHT UNDER 永康路楼下8座chef's table(楼上另有散点)，主厨个人主理
    1926,   # OnCue 1933老场坊仅5桌，提前1-2周预约，创意西餐chef's table
    1930,   # 思南海派私房菜 思南公馆法国别墅内预约制本帮私宴
    1931,   # La Jade 希尔顿内仅10席 invite-only 主厨个人主理 tasting
    1933,   # huma 1095 愚园路8板前，预约极难订，主厨团队个人主理
    1939,   # 北外滩隐世融合私宴 无公开菜单电话，按门铃熟人介绍，真实店名待核
    1941,   # 赉安·海派中式板前 永嘉路花园洋房8板前，微信提前3天预约
]
# 仅移除83：营销"私宴/会馆"但实为有公开门店的连锁/品牌升级餐厅，已有正确菜系
REMOVE_ONLY = [
    1446,   # 釜溪盐韵·私宴 蜀谭记集团总部全包厢川菜，有大众点评 → 归川菜/盐帮
    1517,   # 乾七道文化会馆 商场3楼全包间莆田菜，有大众点评 → 归闽菜/莆仙
    1843,   # 聪菜馆 六合大厦1楼有公开门面，米其林必比登本帮 → 归本帮菜
    1902,   # Ortensia 张园法餐，官网公开预约 → 归法餐
    1903,   # Endo MIX320盘式甜品omakase → 归甜品
    1904,   # Hide the Smoked Room 黑石公寓炭烤餐酒馆，21点后walk-in供水烟 → 归融合/Bistro
    1923,   # 鮨琉璃 禧瑞广场板前寿司 → 归寿司
    1925,   # MIYARAKU宫楽 长乐路怀石 → 归怀石
    1927,   # 鮨心和 板前寿司(已关店) → 归寿司
    1928,   # 奈良本寿司 永嘉路板前寿司 → 归寿司
    1929,   # 吾观·私宴 全息投影商业艺术餐厅，携程可订 → 归融合/创意
    1937,   # 上式楼 酒店3楼4包间中西融合，有推广视频 → 归融合
    1942,   # 繁花滨江私宴 酒店2楼整层包间临江，有大众点评 → 归江浙/海鲜
    1943,   # 林家一·山海宴 金融中心江景包间，连锁台州菜 → 归台州菜
]
# 移除83 + 改挂茶馆(82)：实际是茶馆/茶艺空间
TO_TEAHOUSE = [1989, 1990, 1991, 1992]  # 时相遇/少山集/隐溪/黄庭


def main():
    commit = "--commit" in sys.argv
    h = C.headers()
    rows = C.fetch_all('restaurant_cuisines', select='restaurant_id,cuisine_id,is_primary',
                      order_col='restaurant_id')
    current = {(l['restaurant_id'], l['cuisine_id']): l['is_primary'] for l in rows}

    removes, adds = [], []
    all83 = CLUB + PRIVATE + REMOVE_ONLY + TO_TEAHOUSE
    for rid in all83:
        if (rid, OLD_ID) in current:
            removes.append({'restaurant_id': rid, 'cuisine_id': OLD_ID})
    for rid in CLUB:
        if (rid, CLUB_ID) not in current:
            adds.append({'restaurant_id': rid, 'cuisine_id': CLUB_ID, 'is_primary': False})
    for rid in PRIVATE:
        if (rid, PRIVATE_ID) not in current:
            adds.append({'restaurant_id': rid, 'cuisine_id': PRIVATE_ID, 'is_primary': False})
    for rid in TO_TEAHOUSE:
        if (rid, TEAHOUSE_ID) not in current:
            adds.append({'restaurant_id': rid, 'cuisine_id': TEAHOUSE_ID, 'is_primary': False})

    plan = {'remove_cuisine_83': removes, 'add_links': adds,
            'club': CLUB, 'private': PRIVATE, 'remove_only': REMOVE_ONLY, 'to_teahouse': TO_TEAHOUSE}
    out = pathlib.Path(__file__).parent / 'reclassify_83_plan.json'
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'会所({CLUB_ID}) {len(CLUB)}家: {CLUB}')
    print(f'私房菜({PRIVATE_ID}) {len(PRIVATE)}家: {PRIVATE}')
    print(f'仅移除83 {len(REMOVE_ONLY)}家')
    print(f'改挂茶馆(82) {len(TO_TEAHOUSE)}家')
    print(f'计划删除83关联 {len(removes)} 条；新增关联 {len(adds)} 条')

    if not commit:
        print('\n[DRY-RUN] 未写库。确认后加 --commit 执行。')
        return
    # 执行：先删后增
    hdel = dict(h); hdel['Prefer'] = 'return=representation'
    for rm in removes:
        rr = requests.delete(C.BASE + f"/restaurant_cuisines?restaurant_id=eq.{rm['restaurant_id']}&cuisine_id=eq.{OLD_ID}", headers=h, timeout=30)
        if rr.status_code not in (200, 204):
            print('DEL FAIL', rm, rr.status_code, rr.text[:200])
    print(f'已删除 {len(removes)} 条 83 关联')
    # 批量插入新关联
    if adds:
        ra = requests.post(C.BASE + '/restaurant_cuisines', headers={**h, 'Prefer': 'return=representation'},
                           json=adds, timeout=30)
        print('INSERT status', ra.status_code, ra.text[:300])
    print('[COMMIT] 完成')


if __name__ == '__main__':
    main()

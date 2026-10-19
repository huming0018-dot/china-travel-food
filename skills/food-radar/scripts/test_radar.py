"""Offline regression tests. All restaurants/URLs are synthetic, not recommendations."""
import asyncio
import copy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock

_SELF = sys.modules[__name__]

from radar import Radar, TZ, instant, event_state, query_plan, validate_record, fact_value, semantic_hash
from dianping_fetch import parse_detail, profile_path, search, shop_url

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=TZ)

def source(at=NOW, origin="fixture-official"):
    return {"url":"https://restaurant.example/menu?utm_source=test", "publisher":"虚构测试店",
            "origin_id":origin, "observed_at":at.isoformat(), "published_at":"2026-10-01"}

def fact(value, at=NOW):
    return {"value":value, "basis":"official", "sources":[source(at)]}

def restaurant(rid="r1", branch="甲分店", **facts):
    return {"schema_version":2,"id":rid,"kind":"restaurant","name":"虚构测试餐厅","city":"上海",
            "branch":branch,"sources":[source()],
            "facts":{"business_status":fact("open"),"price_per_head":fact(300),
                     "ingredient_tags":fact(["测试食材"]), "technique_tags":fact(["炭火"]),
                     **{k:fact(v) for k,v in facts.items()}}}

def event(eid="e1", **kw):
    value = {"schema_version":2,"id":eid,"kind":"event","name":"虚构测试客座","city":"上海",
             "restaurant_id":"r1","event_type":"guest_chef","event_status":"announced",
             "starts_at":"2026-10-20T18:00:00+08:00","ends_at":"2026-10-20T22:00:00+08:00",
             "sources":[source()], "facts":{"price_per_head":fact(800),"booking_status":fact("available")}}
    value.update(kw)
    return value


class RadarTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dbpath = Path(self.temp.name)/"private"/"radar.sqlite"
        self.dbpath.parent.mkdir(parents=True, exist_ok=True)
        # db 必须落在宿主固定的数据根内；测试用隔离根，生产由宿主设置。
        self._prev_root = os.environ.get("FOOD_RADAR_DATA_ROOT")
        os.environ["FOOD_RADAR_DATA_ROOT"] = str(self.dbpath.parent)
        self.r = Radar(self.dbpath,"test-group","alice")

    def tearDown(self):
        self.r.close()
        if self._prev_root is None:
            os.environ.pop("FOOD_RADAR_DATA_ROOT", None)
        else:
            os.environ["FOOD_RADAR_DATA_ROOT"] = self._prev_root
        self.temp.cleanup()
        self.temp.cleanup()

    def put(self,*records):
        return self.r.ingest(list(records), NOW)

    def shortlist(self,**kw):
        return self.r.shortlist("上海",now=NOW,**kw)

    def test_basic_shortlist_evidence_and_honest_novelty(self):
        self.put(restaurant())
        x = self.shortlist()["items"][0]
        self.assertEqual(x["price_per_head"],300)
        self.assertIn("没有已记录的到访，不等于你没吃过",x["reasons"])
        self.assertIn("营业中、当天有位、排队情况需分别确认",x["needs_confirmation"])
        self.assertNotIn("utm_",x["record"]["sources"][0]["url"])

    def test_profile_is_explicit_and_feedback_does_not_infer_cuisine(self):
        self.put(restaurant())
        self.r.profile({"experience":"experienced","priorities":["口味","新鲜","特殊食材"]})
        self.r.feedback("r1","这一次的酱汁太甜，不代表讨厌所有甜味","mixed","2026-10-01")
        self.assertEqual(self.r.profile()["avoid_tags"],[])
        self.assertEqual(self.r.profile()["liked_tags"],[])
        self.assertNotIn("没有已记录的到访，不等于你没吃过",self.shortlist()["items"][0]["reasons"])

    def test_personal_exact_tags_and_no_prestige_score(self):
        self.put(restaurant("r1"),restaurant("r2",branch="乙分店",ingredient_tags=["菌菇"]))
        self.r.profile({"liked_tags":["菌菇"],"avoid_tags":["测试食材"]})
        x=self.shortlist()
        self.assertEqual([i["id"] for i in x["items"]],["r2"])
        self.assertTrue(x["excluded"][0]["reason"].startswith("avoid_tags:"))

    def test_required_ingredient_unconfirmed_is_excluded(self):
        self.put(restaurant())
        x=self.shortlist(required_tags=["未确认食材"])
        self.assertEqual(x["items"],[])
        self.assertEqual(x["excluded"][0]["reason"],"required_ingredient_or_technique_unconfirmed")

    def test_stale_price_does_not_invent_budget_fit(self):
        r=restaurant()
        r["facts"]["price_per_head"]=fact(20,NOW-timedelta(days=31))
        self.put(r)
        x=self.shortlist(budget=50)["items"][0]
        self.assertIsNone(x["price_per_head"])
        self.assertIn("预算待确认",x["needs_confirmation"])

    def test_over_budget_excluded(self):
        self.put(restaurant())
        self.assertEqual(self.shortlist(budget=200)["excluded"][0]["reason"],"over_budget")

    def test_unknown_allergens_excluded_and_known_no_guarantee(self):
        self.r.profile({"allergies":["花生"]})
        self.put(restaurant())
        self.assertEqual(self.shortlist()["excluded"][0]["reason"],"allergen_information_unconfirmed")
        self.put(restaurant(allergens=[]))
        self.assertIn("已知过敏原未匹配，仍需门店确认交叉接触",self.shortlist()["items"][0]["needs_confirmation"])
        self.put(restaurant(allergens=["花生"]))
        self.assertEqual(self.shortlist()["excluded"][0]["reason"],"allergen_conflict")

    def test_future_opening_excluded_from_now(self):
        self.put(restaurant(business_status="unknown",opening_date="2026-10-25"))
        self.assertEqual(self.shortlist()["excluded"][0]["reason"],"not_open_yet")
        self.assertEqual(len(self.shortlist(mode="radar")["items"]),1)

    def test_closed_and_temporary_closed_not_recommended(self):
        self.put(restaurant(business_status="closed"))
        self.assertEqual(self.shortlist()["items"],[])
        self.put(restaurant(business_status="temporarily_closed"))
        self.assertEqual(self.shortlist()["items"],[])

    def test_radar_excludes_old_restaurant_but_includes_its_guest_event(self):
        self.put(restaurant(opening_date="2019-01-01"),event())
        result=self.shortlist(mode="radar")
        self.assertEqual([i["id"] for i in result["items"]],["e1"])
        self.assertEqual(result["items"][0]["price_per_head"],800)

    def test_cancelled_postponed_ended_unknown_excluded(self):
        cases=[event(event_status="cancelled"),event(event_status="postponed"),
               event(starts_at="2026-10-01",ends_at="2026-10-02"),
               event(starts_at=None,ends_at=None)]
        for ev in cases:
            with self.subTest(ev=ev):
                self.put(restaurant(),ev)
                self.assertEqual(self.shortlist(mode="radar")["items"],[])

    def test_soldout_is_news_not_bookable(self):
        e=event()
        e["facts"]["booking_status"]=fact("sold_out")
        self.put(restaurant(),e)
        self.assertIn("已售罄",self.shortlist(mode="radar")["items"][0]["needs_confirmation"])

    def test_booking_fifteen_minute_cache(self):
        e=event()
        e["facts"]["booking_status"]=fact("available",NOW-timedelta(minutes=16))
        self.put(restaurant(),e)
        x=self.shortlist(mode="radar")["items"][0]
        self.assertIn("余位待核实；有链接不代表有位",x["needs_confirmation"])

    def test_event_price_never_inherited_from_normal_menu(self):
        e=event(facts={})
        self.put(restaurant(),e)
        x=self.shortlist(mode="radar",budget=500)["items"][0]
        self.assertIsNone(x["price_per_head"])
        self.assertIn("预算待确认",x["needs_confirmation"])

    def test_day_boundary_and_timezone(self):
        self.assertEqual(event_state(event(starts_at="2026-10-18",ends_at="2026-10-18"),NOW),"active")
        self.assertEqual(event_state(event(starts_at="2026-10-18T03:00:00Z",ends_at="2026-10-18T05:00:00Z"),NOW),"active")
        self.assertEqual(event_state(event(starts_at="2026-10-18T01:00:00Z",ends_at="2026-10-18T03:59:59Z"),NOW),"ended")

    def test_cross_year_plan_and_window(self):
        plan=query_plan("成都","radar","2026-12-20","2027-01-10",tags=["菌菇"])
        text=" ".join(plan["queries"])
        self.assertIn("2026年12月",text)
        self.assertIn("2027年01月",text)
        self.assertNotIn("上海",text)
        self.assertTrue(all("成都" in q for q in plan["queries"]))

    def test_overlap_window_excludes_outside(self):
        self.put(restaurant(),event())
        self.assertEqual(self.shortlist(mode="radar",start="2026-11-01",end="2026-11-30")["items"],[])
        self.assertEqual(len(self.shortlist(mode="radar",start="2026-10-20",end="2026-10-20")["items"]),1)

    def test_batch_validation_is_atomic(self):
        bad=restaurant("r2",branch="乙店")
        bad["facts"]["price_per_head"]["sources"]=[]
        with self.assertRaises(ValueError):
            self.put(restaurant(),bad)
        self.assertEqual(self.r.records(),[])

    def test_event_needs_same_city_parent(self):
        with self.assertRaises(ValueError):
            self.put(event())
        e=event(city="成都")
        with self.assertRaises(ValueError):
            self.put(restaurant(),e)
        self.assertEqual(self.r.records(),[])

    def test_identity_collision_and_branch_separation(self):
        self.put(restaurant(),restaurant("r2",branch="乙分店"))
        self.assertEqual(len(self.r.records()),2)
        with self.assertRaises(ValueError):
            self.put(restaurant(branch="乙分店"))
        self.assertEqual(self.r.get("r1")["branch"],"甲分店")

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            self.put(restaurant(),restaurant())

    def test_refresh_not_new_and_menu_change_logged(self):
        r=restaurant()
        self.assertEqual(self.put(r)[0]["change"],"new")
        refreshed=copy.deepcopy(r)
        def refresh(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k=="observed_at": x[k]=(NOW+timedelta(minutes=1)).isoformat()
                    else: refresh(v)
            elif isinstance(x,list):
                for v in x: refresh(v)
        refresh(refreshed)
        self.assertEqual(self.put(refreshed)[0]["change"],"refreshed")
        self.assertEqual(len(self.r.changes()),1)
        refreshed["facts"]["menu"]=fact("新的虚构菜单")
        self.assertEqual(self.put(refreshed)[0]["change"],"updated")
        self.assertEqual(len(self.r.changes(after=1)),1)

    def test_scopes_isolate_records_profile_wishlist_feedback_changes(self):
        self.put(restaurant())
        self.r.save("r1","纪念日")
        self.r.profile({"liked_tags":["炭火"]})
        self.r.feedback("r1","测试反馈","liked","2026-10-01")
        for surface,actor in [("test-group","bob"),("other-group","alice")]:
            other=Radar(self.dbpath,surface,actor)
            try:
                self.assertEqual(other.records(),[])
                self.assertEqual(other.wishlist(),[])
                self.assertEqual(other.history("r1"),[])
                self.assertEqual(other.changes(),[])
                self.assertEqual(other.profile()["liked_tags"],[])
                with self.assertRaises(ValueError): other.save("r1")
            finally: other.close()

    def test_wishlist_persists_and_unsave_does_not_delete_record(self):
        self.put(restaurant())
        self.r.save("r1","想吃炭火")
        self.r.close()
        self.r=Radar(self.dbpath,"test-group","alice")
        self.assertEqual(self.r.wishlist()[0]["note"],"想吃炭火")
        self.r.unsave("r1")
        self.assertEqual(self.r.wishlist(),[])
        self.assertEqual(self.r.get("r1")["id"],"r1")

    def test_invalid_timestamps_sources_and_future_publication(self):
        for mutate in [
            lambda r:r["sources"][0].update(observed_at="2026-10-18T12:00:00"),
            lambda r:r["sources"][0].update(published_at="2026-12-01"),
            lambda r:r["sources"][0].update(url="https://user:secret@example.com"),
            lambda r:r.update(schema_version=1),
            lambda r:r.update(sources=[]),
        ]:
            with self.subTest(mutate=mutate):
                r=restaurant();mutate(r)
                with self.assertRaises(ValueError): self.put(r)

    def test_valid_until_shortens_cache(self):
        r=restaurant()
        r["facts"]["price_per_head"]["valid_until"]=(NOW-timedelta(seconds=1)).isoformat()
        self.assertIsNone(fact_value(r,"price_per_head",NOW))

    def test_guest_menu_does_not_inherit_normal_ingredients(self):
        self.put(restaurant(),event())
        self.assertEqual(self.shortlist(mode="radar",required_tags=["测试食材"])["items"],[])

    def test_old_closure_does_not_expire_into_recommendation(self):
        r=restaurant()
        r["facts"]["business_status"]=fact("closed",NOW-timedelta(days=60))
        self.put(r)
        self.assertEqual(self.shortlist()["items"],[])

    def test_old_menu_tags_cannot_prove_special_ingredient(self):
        r=restaurant()
        r["facts"]["ingredient_tags"]=fact(["测试食材"],NOW-timedelta(days=31))
        self.put(r)
        self.assertEqual(self.shortlist(required_tags=["测试食材"])["items"],[])

    def test_backfilled_visit_does_not_overwrite_latest_experience(self):
        self.put(restaurant())
        self.r.feedback("r1","最近一次喜欢","liked","2026-10-10")
        self.r.feedback("r1","补记更早一次不好吃","disliked","2026-10-01")
        self.assertEqual(self.r.history("r1")[-1]["verdict"],"liked")
        self.assertNotIn("上次评价不喜欢，复访需要新理由",self.shortlist()["items"][0]["reasons"])

    def test_bad_limit_nan_budget_and_window(self):
        for kw in [{"limit":0},{"budget":float("nan")},{"start":"2026-11-01","end":"2026-10-01"}]:
            with self.assertRaises(ValueError): self.shortlist(**kw)


class CollectorTest(unittest.TestCase):
    def test_only_labeled_visible_fields(self):
        x=parse_detail("口味 4.8\n环境4.9\n服务4.7\n人均：￥328\n地址：测试路1号\n营业时间：18:00-22:00",
                       '<script>{"rating":5.0}</script>')
        self.assertIsNone(x["score"])
        self.assertEqual(x["price"],328)
        self.assertEqual(x["address"],"测试路1号")
        self.assertTrue(x["requires_visual_verification"])

    def test_explicit_score_and_unknowns(self):
        x=parse_detail("4.7 分数\n123 条评价")
        self.assertEqual(x["score"],4.7)
        self.assertEqual(x["review_count"],123)
        self.assertIsNone(x["address"])
        self.assertIsNone(x["open_time"])

    def test_shop_urls_restrict_external_targets(self):
        self.assertEqual(shop_url("/shop/abc123?utm_source=xx"),"https://www.dianping.com/shop/abc123")
        for value in ["https://evil.example/shop/a","https://www.dianping.com.evil.example/shop/a",
                      "https://user:pass@www.dianping.com/shop/a","https://www.dianping.com/login"]:
            with self.assertRaises(ValueError): shop_url(value)

    def test_browser_profile_is_scope_specific(self):
        self.assertNotEqual(profile_path("/tmp","group","a"),profile_path("/tmp","group","b"))
        self.assertNotEqual(profile_path("/tmp","group","a"),profile_path("/tmp","other","a"))

    def test_search_uses_city_and_deduplicates_visible_links(self):
        page=AsyncMock()
        links=AsyncMock()
        # locator() is synchronous in Playwright; its awaited methods are asynchronous.
        page.locator=lambda _:links
        links.evaluate_all.return_value=[
            {"name":"店甲","url":"/shop/a1?utm_source=x"},
            {"name":"店甲","url":"https://www.dianping.com/shop/a1"},
            {"name":"坏链接","url":"https://evil.example/shop/xx"},
            {"name":"店乙","url":"/shop/b2"}]
        x=asyncio.run(search(page,"测试店",8))
        self.assertEqual(len(x["results"]),2)
        self.assertIn("/keyword/8/",page.goto.call_args.args[0])
        self.assertEqual(x["status"],"observed")

    def test_failure_is_not_zero_results_claim(self):
        page=AsyncMock()
        links=AsyncMock()
        page.locator=lambda _:links
        links.first.wait_for.side_effect=TimeoutError()
        x=asyncio.run(search(page,"测试",1))
        self.assertEqual(x["status"],"channel_unverified")
        self.assertIn("not proof",x["reason"])


class CLITest(unittest.TestCase):
    def test_cli_end_to_end_and_durable_state(self):
        with tempfile.TemporaryDirectory() as td:
            script=Path(__file__).with_name("radar.py")
            db=Path(td)/"data.sqlite"
            inputfile=Path(td)/"fixture.json"
            live_now = datetime.now(TZ)
            fixture = json.dumps([restaurant()],ensure_ascii=False).replace(NOW.isoformat(), live_now.isoformat()).replace("2026-10-01", live_now.date().isoformat())
            inputfile.write_text(fixture)
            common=["--db",str(db),"--surface","fixture","--actor","alice"]
            env=dict(os.environ, FOOD_RADAR_DATA_ROOT=str(Path(td).resolve()))
            def call(cmd,*args):
                p=subprocess.run([sys.executable,str(script),cmd,*common,*args],
                                 capture_output=True,text=True,env=env)
                self.assertEqual(p.returncode,0,p.stderr)
                return json.loads(p.stdout)
            self.assertEqual(call("ingest","--input",str(inputfile))[0]["change"],"new")
            call("save","--id","r1","--note","测试想吃")
            self.assertEqual(call("wishlist")[0]["note"],"测试想吃")
            self.assertEqual(call("shortlist","--city","上海","--at",live_now.isoformat())["items"][0]["id"],"r1")
            self.assertEqual(len(call("changes")),1)


class MergeAddedTest(unittest.TestCase):
    """合并新增行为的回归：db 路径守卫 + 推荐菜/团购解析。"""

    def test_db_must_live_under_host_fixed_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "allowed"; root.mkdir()
            env_prev = os.environ.get("FOOD_RADAR_DATA_ROOT")
            os.environ["FOOD_RADAR_DATA_ROOT"] = str(root)
            try:
                ok = Radar(root / "r.sqlite", "g", "a")
                ok.close()
                # 逃逸到根之外必须拒绝
                for bad in (Path(td) / "outside.sqlite",
                            root / ".." / "escape.sqlite"):
                    with self.assertRaises(ValueError):
                        Radar(bad, "g", "a")
                # 根之外的不同名子目录同样拒绝（必须"直接位于"根下）
                sub = root / "nested"; sub.mkdir()
                with self.assertRaises(ValueError):
                    Radar(sub / "x.sqlite", "g", "a")
            finally:
                if env_prev is None:
                    os.environ.pop("FOOD_RADAR_DATA_ROOT", None)
                else:
                    os.environ["FOOD_RADAR_DATA_ROOT"] = env_prev

    def test_parse_recommended_handles_three_layouts(self):
        from dianping_fetch import parse_recommended
        two_col = ("网友推荐(31)\n17人推荐\n16人推荐\n8人推荐\n"
                   "玛德琳\n战斧猪排\n鳗鱼\n去大众点评App查看全部31道推荐菜")
        self.assertEqual(
            [(d["name"], d["votes"]) for d in parse_recommended(two_col)],
            [("玛德琳", 17), ("战斧猪排", 16), ("鳗鱼", 8)])
        same_line = "网友推荐(2)\n17人推荐 玛德琳\n16人推荐 战斧猪排"
        self.assertEqual(
            [(d["name"], d["votes"]) for d in parse_recommended(same_line)],
            [("玛德琳", 17), ("战斧猪排", 16)])
        stacked = "网友推荐(2)\n17人推荐\n玛德琳\n16人推荐\n战斧猪排"
        self.assertEqual(
            [(d["name"], d["votes"]) for d in parse_recommended(stacked)],
            [("玛德琳", 17), ("战斧猪排", 16)])
        self.assertEqual(parse_recommended("网友推荐(0)\n暂无"), [])

    def test_parse_group_buy_only_matches_bracketed_sets(self):
        from dianping_fetch import parse_group_buy
        text = ("【四时风物】相遇江南双人宴\n¥998\n原价¥1465.2\n"
                "【山水入席】江南相聚六人宴｜包厢可用\n¥2980\n其他说明 ¥50")
        out = parse_group_buy(text)
        self.assertEqual([(o["set"], o["price_cny"]) for o in out],
                         [("【四时风物】相遇江南双人宴", 998.0),
                          ("【山水入席】江南相聚六人宴｜包厢可用", 2980.0)])
        self.assertEqual(parse_group_buy("无团购信息"), [])

    def test_recommended_stops_at_address_block(self):
        """#23 两列布局遇到地址段必须截断，不能把门牌号当成菜名。"""
        from dianping_fetch import parse_recommended
        text = ("网友推荐(2)\n17人推荐\n16人推荐\n"
                "玛德琳\n战斧猪排\n"
                "地址：建国西路485-1号\n电话：021-1234\n")
        out = parse_recommended(text)
        self.assertEqual([d["name"] for d in out], ["玛德琳", "战斧猪排"])
        self.assertTrue(all("地址" not in d["name"] for d in out))

    def test_group_buy_last_set_stops_at_body_boundary(self):
        """#24 最后一个套餐没有下一个【作右界时，不能借用正文后面的人均金额。"""
        from dianping_fetch import parse_group_buy
        text = ("【双人宴】江南风味\n¥998\n"
                "【六人宴】包厢可用\n无标价\n"
                "人均：¥298\n网友推荐(10)\n")
        out = parse_group_buy(text)
        self.assertEqual(out[0]["price_cny"], 998.0)
        self.assertIsNone(out[1]["price_cny"])

    def test_group_buy_original_counterexamples(self):
        """#24 原始反例：末段不得吃进正文金额；订金不得当套餐价。"""
        from dianping_fetch import parse_group_buy
        # 反例1：无价套餐 + 网友评论 + 停车费
        r1 = parse_group_buy("【套餐甲】双人宴\n暂无价格\n网友评论\n停车费¥50")
        self.assertEqual(len(r1), 1)
        self.assertIsNone(r1[0]["price_cny"])
        # 反例2：订金 100、套餐价 800
        r2 = parse_group_buy("【套餐甲】双人宴\n订金¥100\n套餐价¥800")
        self.assertEqual(r2[0]["price_cny"], 800.0)

    def test_merge_detail_records_conflicts(self):
        """#26 DOM 与文本锚定不一致时必须记录冲突，不能静默采信 DOM。"""
        from dianping_fetch import merge_detail
        dom = {"score": 4.8, "price": None, "address": None, "name": None,
               "review_count": None, "open_time": None, "parser": "dom-strict-v1"}
        txt = {"score": 4.5, "price": None, "address": None, "name": None,
               "review_count": None, "open_time": None, "parser": "visible-labelled-text-v2"}
        m = merge_detail(dom, txt)
        # 冲突时保守留空：DOM 并非可信一方（它也曾把"38人推荐"当价格），
        # 给一个可能错的值比留空更危险。
        self.assertIsNone(m["score"])
        self.assertIn("score", m["conflicts"])
        self.assertEqual(m["conflicts"]["score"]["dom"], 4.8)
        self.assertEqual(m["conflicts"]["score"]["text"], 4.5)
        self.assertIsNone(m["conflicts"]["score"]["taken"])

    def test_parse_group_buy_real_page_layout(self):
        """真实点评页面：套餐名、有效期、¥符号、数字分散在多行。"""
        from dianping_fetch import parse_group_buy
        real = ("\u3010\u5c71\u6c34\u5165\u5e2d\u3011\u6c5f\u5357\u76f8\u805a\u516d\u4eba\u5bb4\uff5c\u5305\u53a2\u53ef\u7528\n"
                "\u5468\u4e00\u81f3\u5468\u65e5\n\u968f\u65f6\u9000\n\u8fc7\u671f\u81ea\u52a8\u9000\n\u00a5\n2980\n7.1\u6298\n\uffe5\u0034\u0032\u0034\u0031\u002e\u0036\n\u63a8\u8350\u83dc")
        out = parse_group_buy(real)
        self.assertEqual(len(out), 1, out)
        self.assertEqual(out[0]["price_cny"], 2980.0)
        self.assertIn("\u5c71\u6c34\u5165\u5e2d", out[0]["set"])


class DomStrictParseTest(unittest.TestCase):
    """DOM 解析必须逐字段校验形状——2026-10-18 实测宽松选择器曾把
    '38人推荐' 当成评价数，属静默造假。此类值必须被丢弃。"""

    def _page(self, mapping):
        class N:
            def __init__(self, v): self.v = v
            async def inner_text(self): return self.v
        class P:
            async def query_selector(self, sel):
                return N(mapping[sel]) if sel in mapping else None
        return P()

    def _run(self, page):
        import asyncio
        from dianping_fetch import parse_detail_dom
        return asyncio.run(parse_detail_dom(page))

    def test_rejects_wrong_shape_values(self):
        r = self._run(self._page({
            "#comment_score .score": "4.7",
            "#reviewCount": "38人推荐",          # 形状不符
            "#addressTxt": "北外滩街道,新建路200号国华金融中心P1-L4",
            ".avg-price-title": "人均￥388",
        }))
        self.assertEqual(r["score"], 4.7)
        self.assertIsNone(r["review_count"])            # 关键：不能接受 "38人推荐"
        self.assertIn("新建路200号", r["address"])
        self.assertEqual(r["price"], 388.0)

    def test_score_range_and_price_bounds(self):
        r = self._run(self._page({"#comment_score .score": "9.9",
                                  ".avg-price-title": "人均￥99999999"}))
        self.assertIsNone(r["score"])                   # >5 丢弃
        self.assertIsNone(r["price"])                   # 超界丢弃

    def test_address_must_look_like_an_address(self):
        r = self._run(self._page({"#addressTxt": "查看地图"}))
        self.assertIsNone(r["address"])

    def test_score_over_five_rejected_and_selector_falls_back(self):
        """#25 反例1与3：5.9 超上限必须拒绝；首个 selector 不合格要继续尝试下一个。"""
        r = self._run(self._page({
            "#comment_score .score": "无评分",       # 形状不符 → 继续
            ".comment-score .score": "4.7",          # 合法 → 采用
            "[class*=avgPrice]": "38人推荐",         # 无价格语义 → 继续
            ".avg-price-title": "人均￥388",          # 合法 → 采用
        }))
        self.assertEqual(r["score"], 4.7)
        self.assertEqual(r["price"], 388.0)

        r2 = self._run(self._page({"#comment_score .score": "5.9",
                                   ".avg-price-title": "38人推荐"}))
        self.assertIsNone(r2["score"])               # 超满分丢弃
        self.assertIsNone(r2["price"])               # 人数不是价格

    def test_low_price_with_explicit_semantics_is_kept(self):
        """#25 反例2：人均￥8 语义明确，不能被数值门槛误杀。"""
        r = self._run(self._page({".avg-price-title": "人均￥8"}))
        self.assertEqual(r["price"], 8.0)

    def test_always_flags_visual_verification(self):
        r = self._run(self._page({}))
        self.assertTrue(r["requires_visual_verification"])
        for k in ("name", "score", "price", "review_count", "address", "open_time"):
            self.assertIsNone(r[k])

    def test_merge_prefers_dom_then_falls_back(self):
        from dianping_fetch import merge_detail
        merged = merge_detail(
            {"name": None, "score": 4.7, "price": None, "review_count": None,
             "address": "A", "open_time": None, "parser": "dom-strict-v1"},
            {"name": "文本名", "score": None, "price": 388.0, "review_count": 98,
             "address": None, "open_time": "11:30-14:00"})
        self.assertEqual(merged["score"], 4.7)           # DOM 优先
        self.assertEqual(merged["price"], 388.0)         # DOM 缺 → 文本兜底
        self.assertEqual(merged["name"], "文本名")
        self.assertEqual(merged["address"], "A")
        self.assertTrue(merged["requires_visual_verification"])


    def test_parse_group_buy_no_cross_set_price_borrowing(self):
        """2026-10-18 审查发现：上一套餐无价格时会吃到下一套餐的价格——
        把¥2980 安到无价套餐上属于编造数据。价格必须来自本段。"""
        from dianping_fetch import parse_group_buy
        text = ("\u3010\u5957\u9910A\u3011\u53cc\u4eba\u5bb4\n\u968f\u65f6\u9000\n\u8fc7\u671f\u81ea\u52a8\u9000\n"
                "\u3010\u5957\u9910B\u3011\u516d\u4eba\u5bb4\n\u00a5\n2980")
        out = parse_group_buy(text)
        self.assertEqual(len(out), 2)
        self.assertIsNone(out[0]["price_cny"], "无价套餐不得借用下一套餐的价格")
        self.assertEqual(out[1]["price_cny"], 2980.0)
        # 单个套餐无任何价格时不应凭空产生条目
        only_a = parse_group_buy("\u3010\u5957\u9910A\u3011\u53cc\u4eba\u5bb4\n\u968f\u65f6\u9000")
        self.assertEqual([o["price_cny"] for o in only_a], [None])

    def test_parse_group_buy_real_multi_line_layout(self):
        from dianping_fetch import parse_group_buy
        real = ("\u3010\u56db\u65f6\u98ce\u7269\u3011\u76f8\u9047\u6c5f\u5357\u53cc\u4eba\u5bb4\n\u4eca\u65e5\u53ef\u7528\n\u00a5\n998\n"
                "\u3010\u5c71\u6c34\u5165\u5e2d\u3011\u6c5f\u5357\u76f8\u805a\u516d\u4eba\u5bb4\uff5c\u5305\u53a2\u53ef\u7528\n\u5468\u4e00\u81f3\u5468\u65e5\n\u00a5\n2980")
        out = parse_group_buy(real)
        self.assertEqual([o["price_cny"] for o in out], [998.0, 2980.0])


class DianpingBoundaryRegressionTest(unittest.TestCase):
    def test_issue23_partial_two_column_section_stays_unknown(self):
        from dianping_fetch import parse_recommended
        text = "网友推荐\\n17人推荐\\n16人推荐\\n玛德琳\\n地址：测试路1号"
        self.assertEqual(parse_recommended(text), [])

    def test_recommendation_does_not_cross_layout_footer_or_address(self):
        from dianping_fetch import parse_recommended
        text = ("网友推荐(2)\\n17人推荐\\n16人推荐\\n玛德琳\\n战斧猪排\\n"
                "地址：测试路1号\\n电话：021-1234")
        self.assertEqual(parse_recommended(text), [
            {"name": "玛德琳", "votes": 17},
            {"name": "战斧猪排", "votes": 16},
        ])

    def test_issue24_last_package_does_not_use_parking_price(self):
        from dianping_fetch import parse_group_buy
        rows = parse_group_buy("【套餐甲】双人宴\\n暂无价格\\n网友评论\\n停车费¥50")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["price_cny"])

    def test_issue25_dom_price_requires_per_person_semantics(self):
        from dianping_fetch import parse_detail_dom
        page = DomStrictParseTest()._page({
            "#comment_score .score": "5.9",
            ".avg-price-title": "停车费¥50",
        })
        result = asyncio.run(parse_detail_dom(page))
        self.assertIsNone(result["score"])
        self.assertIsNone(result["price"])



class CalendarTest(unittest.TestCase):
    """未来日历视图：按日期排活动；取消/延期/已结束/档期不明各自归位，
    且绝不能混入可订项。NOW = 2026-10-18 12:00 +08:00。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dbpath = Path(self.temp.name) / "private" / "radar.sqlite"
        self.dbpath.parent.mkdir(parents=True, exist_ok=True)
        self._prev = os.environ.get("FOOD_RADAR_DATA_ROOT")
        os.environ["FOOD_RADAR_DATA_ROOT"] = str(self.dbpath.parent)
        # ingest 用真实 now 校验 observed_at，而 NOW=12:00 晚于真实时钟，
        # 故本类内统一改用"已发生"的观测时间。
        self._orig_source = _SELF.source
        _orig = self._orig_source          # 闭包捕获，避免 lambda 递归调用自身
        _SELF.source = (lambda at=None, origin="fixture-official":
                        _orig(at=datetime(2026, 10, 18, 1, 30, tzinfo=_SELF.TZ),
                              origin=origin))
        self.r = Radar(self.dbpath, "g", "alice")

    def tearDown(self):
        self.r.close()
        _SELF.source = self._orig_source
        if self._prev is None:
            os.environ.pop("FOOD_RADAR_DATA_ROOT", None)
        else:
            os.environ["FOOD_RADAR_DATA_ROOT"] = self._prev
        self.temp.cleanup()

    CAL_NOW = datetime(2026, 10, 18, 1, 35, tzinfo=TZ)   # 贴近真实时钟
    WIN_FROM, WIN_TO = "2026-10-17", "2026-11-01"

    @classmethod
    def past_source(cls):
        """observed_at 必须 <= 真实 now，且距 CAL_NOW 不超过 booking 的15 分钟 TTL。"""
        return source(at=datetime(2026, 10, 18, 1, 30, tzinfo=TZ))

    def _ingest(self, recs):
        self.r.ingest(recs)

    def test_groups_events_by_date_and_orders_within_day(self):
        self._ingest([
            restaurant(),
            event(eid="late", starts_at="2026-10-20T20:00:00+08:00",
                  ends_at="2026-10-20T22:00:00+08:00", name="晚场"),
            event(eid="early", starts_at="2026-10-20T18:00:00+08:00",
                  ends_at="2026-10-20T20:00:00+08:00", name="早场"),
            event(eid="next", starts_at="2026-10-21T18:00:00+08:00",
                  ends_at="2026-10-21T20:00:00+08:00", name="次日"),
        ])
        cal = self.r.calendar("上海", self.WIN_FROM, self.WIN_TO, self.CAL_NOW)
        self.assertEqual(list(cal["by_date"]), ["2026-10-20", "2026-10-21"])
        self.assertEqual([e["name"] for e in cal["by_date"]["2026-10-20"]], ["早场", "晚场"])
        self.assertEqual(cal["counts"]["scheduled"], 3)

    def test_later_flags_unknown_opening_date(self):
        """#18 输入A：planned 且无 opening_date，必须明确提示开业日期未知。"""
        self._ingest([restaurant(business_status="planned")])
        res = self.r.shortlist("上海", mode="later", start="2026-10-20",
                               end="2026-10-21", now=self.CAL_NOW)
        item = res["items"][0]
        self.assertTrue(any("开业日期未知" in n for n in item["needs_confirmation"]))

    def test_later_flags_partial_window(self):
        """#18 输入B：开业日落在窗口内但晚于起始日，必须说明可用日期限制。"""
        self._ingest([restaurant(business_status="planned", opening_date="2026-10-21")])
        res = self.r.shortlist("上海", mode="later", start="2026-10-20",
                               end="2026-10-21", now=self.CAL_NOW)
        item = res["items"][0]
        self.assertTrue(any("计划 2026-10-21 开业" in n for n in item["needs_confirmation"]))

    def test_calendar_orders_by_parsed_time_across_timezones(self):
        """#22 同日组内排序必须按解析后的时间，不能按原始 ISO 字符串。"""
        early = event(eid="z-early", starts_at="2026-10-20T09:00:00+08:00",
                      ends_at="2026-10-20T10:00:00+08:00")
        late = event(eid="a-late", starts_at="2026-10-20T02:00:00Z",
                     ends_at="2026-10-20T03:00:00Z")
        self._ingest([restaurant(), early, late])
        cal = self.r.calendar("上海", self.WIN_FROM, self.WIN_TO, self.CAL_NOW)
        self.assertEqual([x["id"] for x in cal["by_date"]["2026-10-20"]],
                         ["z-early", "a-late"])

    def test_cancelled_postponed_ended_go_to_unavailable_never_bookable(self):
        self._ingest([
            restaurant(),
            event(eid="cx", event_status="cancelled"),
            event(eid="pp", event_status="postponed"),
            # 已结束但落在窗口内（今天凌晨）——窗口外的历史活动不进日历
            event(eid="en", starts_at="2026-10-17T01:00:00+08:00",
                  ends_at="2026-10-17T03:00:00+08:00"),
        ])
        cal = self.r.calendar("上海", self.WIN_FROM, self.WIN_TO, self.CAL_NOW)
        self.assertEqual(cal["counts"]["scheduled"], 0)
        got = {e["id"]: e for e in cal["unavailable"]}
        self.assertEqual(got["cx"]["event_status"], "cancelled")
        self.assertEqual(got["pp"]["event_status"], "postponed")
        self.assertEqual(got["en"]["event_status"], "ended")
        for e in cal["unavailable"]:
            # 不可订项**不得**带时间轴字段，避免被误读为"还能订"
            self.assertIsNone(e.get("starts_at"))
            self.assertIsNone(e.get("needs_confirmation"))
            self.assertTrue(e["reason"])

    def test_undated_events_do_not_enter_date_axis(self):
        self._ingest([restaurant(), event(eid="nd", starts_at=None, ends_at=None)])
        cal = self.r.calendar("上海", self.WIN_FROM, self.WIN_TO, self.CAL_NOW)
        self.assertEqual(cal["counts"]["scheduled"], 0)
        self.assertEqual(cal["undated"][0]["id"], "nd")

    def test_out_of_window_events_absent_entirely(self):
        self._ingest([restaurant(),
                      event(eid="far", starts_at="2027-06-01T18:00:00+08:00",
                            ends_at="2027-06-01T20:00:00+08:00")])
        cal = self.r.calendar("上海", self.WIN_FROM, self.WIN_TO, self.CAL_NOW)
        self.assertEqual(cal["counts"]["scheduled"], 0)
        self.assertEqual(cal["unavailable"], [])

    def test_booking_status_drives_why_now_and_confirmation(self):
        self._ingest([
            restaurant(),
            event(eid="ok", starts_at="2026-10-25T18:00:00+08:00",
                  ends_at="2026-10-25T20:00:00+08:00",
                  facts={"booking_status": {"value": "available", "basis": "booking",
                                            "sources": [self.past_source()],
                                            "valid_until": "2026-10-19T00:00:00+08:00"}}),
            event(eid="sold", starts_at="2026-10-26T18:00:00+08:00",
                  ends_at="2026-10-26T20:00:00+08:00",
                  facts={"booking_status": {"value": "sold_out", "basis": "booking",
                                            "sources": [self.past_source()],
                                            "valid_until": "2026-10-19T00:00:00+08:00"}}),
        ])
        cal = self.r.calendar("上海", self.WIN_FROM, self.WIN_TO, self.CAL_NOW)
        e = {x["id"]: x for v in cal["by_date"].values() for x in v}
        self.assertEqual(e["ok"]["needs_confirmation"], [])
        self.assertTrue(e["sold"]["needs_confirmation"])
        self.assertIn("不可订", e["sold"]["needs_confirmation"][0])
        # 10-25 距 CAL_NOW(10-18) 恰为 7 天 → 判「临近开始」
        self.assertEqual(e["ok"]["why_now"], "临近开始")

    def test_multiday_event_reports_span(self):
        self._ingest([restaurant(),
                      event(eid="span", starts_at="2026-10-30T18:00:00+08:00",
                            ends_at="2026-11-02T22:00:00+08:00")])
        cal = self.r.calendar("上海", self.WIN_FROM, self.WIN_TO, self.CAL_NOW)
        e = cal["by_date"]["2026-10-30"][0]
        self.assertEqual(e["spans_days"], 3)


if __name__ == "__main__":
    unittest.main()

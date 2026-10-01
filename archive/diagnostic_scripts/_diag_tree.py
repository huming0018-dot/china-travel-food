import sys, pathlib
sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common as C

cuisines = C.fetch_all("cuisines", "id,name,parent_category,dimension",
                       use_service=True, order_col="id")
food = [c for c in cuisines if c.get("dimension") == "菜系"]
by_name = {c["name"]: c for c in food}

numeric, name_ok, rootish, orphan = [], [], [], []
for c in food:
    p = c.get("parent_category")
    if p is None or p == "":
        rootish.append(c)
        continue
    ps = str(p).strip()
    if ps.isdigit():
        numeric.append(c)
    elif ps in by_name:
        name_ok.append(c)
    else:
        orphan.append(c)

print("菜系总数:", len(food))
print("parent=名字(正常):", len(name_ok))
print("parent=数字ID(前端不可见):", len(numeric))
print("parent 为空(根):", len(rootish))
print("parent 非名非数(孤儿):", len(orphan))

print("\n--- 数字ID parent 的节点（前40）---")
for c in numeric[:40]:
    pid = int(str(c["parent_category"]).strip())
    pn = next((x["name"] for x in food if x["id"] == pid), "?ID不存在")
    print(f'  id{c["id"]} "{c["name"]}" -> parent id{pid} = "{pn}"')

print("\n--- 孤儿（前20）---")
for c in orphan[:20]:
    print(f'  id{c["id"]} "{c["name"]}" -> parent "{c["parent_category"]}"')

# 抽样：几个应有三级的二级菜，按名字能找到几个孩子
for parent_name in ["川菜", "粤菜", "拉面", "日料/日本料理", "寿司"]:
    kids_name = [c["name"] for c in food if str(c.get("parent_category")) == parent_name]
    print(f"\n[{parent_name}] 按名字直接匹配孩子 {len(kids_name)}: {kids_name[:12]}")

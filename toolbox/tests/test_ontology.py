"""M4 本体库测试：verify（正/反例）+ install 幂等 + ledger + pack_sha256 确定性。

不删除任何目录：临时坏包用 tempfile.mkdtemp 创建后保留。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from toolbox.ontology import (
    PackError,
    install_pack,
    list_packs,
    pack_sha256,
    verify_pack,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FOOD_CN_V2 = REPO_ROOT / "packs" / "food-cn-v2"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class VerifyPackTest(unittest.TestCase):
    def test_food_cn_v2_is_valid(self) -> None:
        errors = verify_pack(FOOD_CN_V2)
        self.assertEqual([], errors)

    def test_missing_pack_yaml(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="ctfs-ont-missing-yaml-"))
        errors = verify_pack(d)
        self.assertTrue(any("pack.yaml" in e for e in errors))

    def test_missing_required_file(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="ctfs-ont-missing-file-"))
        _write(
            d / "pack.yaml",
            "name: bad-pack\nversion: 1.0.0\ndomain: food\n"
            "files:\n  taxonomy: taxonomy.yaml\n  keyword_roots: keyword_roots.json\n"
            "  scoring_rules: scoring_rules.yaml\n  regression_set: regression_set.json\n"
            "  source_plan: source_plan.yaml\n  schemas:\n    - schema/x.schema.json\n",
        )
        errors = verify_pack(d)
        names = " ".join(errors)
        for rel in ("taxonomy.yaml", "keyword_roots.json", "scoring_rules.yaml",
                    "regression_set.json", "source_plan.yaml", "schema/x.schema.json"):
            self.assertIn(rel, names, msg=names)

    def test_invalid_pack_yaml_version(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="ctfs-ont-bad-version-"))
        _write(
            d / "pack.yaml",
            "name: bad-pack\nversion: not-semver\ndomain: food\n"
            "files:\n  taxonomy: taxonomy.yaml\n  keyword_roots: keyword_roots.json\n"
            "  scoring_rules: scoring_rules.yaml\n  regression_set: regression_set.json\n"
            "  source_plan: source_plan.yaml\n  schemas:\n    - schema/x.schema.json\n",
        )
        errors = verify_pack(d)
        self.assertTrue(any("pack.schema.json" in e for e in errors), msg=errors)

    def test_bad_yaml_unparsable(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="ctfs-ont-bad-yaml-"))
        _write(
            d / "pack.yaml",
            "name: bad-pack\nversion: 1.0.0\ndomain: food\n"
            "files:\n  taxonomy: taxonomy.yaml\n  keyword_roots: keyword_roots.json\n"
            "  scoring_rules: scoring_rules.yaml\n  regression_set: regression_set.json\n"
            "  source_plan: source_plan.yaml\n  schemas:\n    - schema/x.schema.json\n",
        )
        for rel in ("taxonomy.yaml", "scoring_rules.yaml", "source_plan.yaml"):
            _write(d / rel, "a: [unclosed\n")
        for rel in ("keyword_roots.json", "regression_set.json"):
            _write(d / rel, "{broken")
        _write(d / "schema" / "x.schema.json", "{}")
        errors = verify_pack(d)
        self.assertTrue(any("解析失败" in e for e in errors), msg=errors)


class InstallLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = Path(tempfile.mkdtemp(prefix="ctfs-ont-ledger-")) / "ledger.json"

    def test_install_then_list(self) -> None:
        entry = install_pack(FOOD_CN_V2, self.ledger)
        self.assertEqual("food-cn", entry.name)
        self.assertEqual("2.0.0", entry.version)
        self.assertEqual(64, len(entry.sha256))
        self.assertTrue(self.ledger.is_file())
        records = list_packs(self.ledger)
        self.assertEqual(1, len(records))
        self.assertEqual("food-cn", records[0]["name"])

    def test_install_idempotent_rejects_duplicate(self) -> None:
        install_pack(FOOD_CN_V2, self.ledger)
        with self.assertRaises(PackError):
            install_pack(FOOD_CN_V2, self.ledger)
        self.assertEqual(1, len(list_packs(self.ledger)))

    def test_install_rejects_invalid_pack(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="ctfs-ont-install-bad-"))
        _write(d / "pack.yaml", "name: bad\nversion: 1.0.0\n")
        with self.assertRaises(PackError):
            install_pack(d, self.ledger)

    def test_list_empty_ledger(self) -> None:
        self.assertEqual([], list_packs(self.ledger))


class PackShaTest(unittest.TestCase):
    def test_pack_sha256_deterministic(self) -> None:
        from toolbox.ontology import load_pack

        pack = load_pack(FOOD_CN_V2)
        self.assertEqual(
            pack_sha256(FOOD_CN_V2, pack), pack_sha256(FOOD_CN_V2, pack)
        )
        self.assertEqual(64, len(pack_sha256(FOOD_CN_V2, pack)))


if __name__ == "__main__":
    unittest.main()

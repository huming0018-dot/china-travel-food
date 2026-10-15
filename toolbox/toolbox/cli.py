"""统一 CLI（PRD §3/§6.4 范式）：toolbox <module> <action> --project <name>

Phase 0 命令：
- init               生成项目 Manifest 模板（projects/ 结构）
- manifest validate  校验 Manifest
- schema list        列出四层 + manifest 契约
- schema validate    按契约校验数据文件
- ontology verify    校验本体包（pack.yaml + 六件套）
- ontology install   登记本体包到 ledger（幂等）
- ontology list      列出已安装本体包
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from .manifest import load_manifest, validate_manifest
from .ontology import list_packs, verify_pack, install_pack
from .schema import SCHEMA_NAMES, load_schema, validate_data

app = typer.Typer(help="CTFS 模块化数据中台 toolbox（PRD v2.1 Phase 0）")
schema_app = typer.Typer(help="数据契约操作")
app.add_typer(schema_app, name="schema")
ontology_app = typer.Typer(help="本体包操作")
app.add_typer(ontology_app, name="ontology")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
DEFAULT_LEDGER = Path("packs/ledger.json")


def _load_manifest_schema() -> dict:
    from .schema import load_schema

    return load_schema("manifest")


@app.command("init")
def init(
    domain: str = typer.Option(..., "--domain", help="领域，如 food / housing"),
    city: str = typer.Option(..., "--city", help="城市，如 shanghai / nj"),
    output: Path = typer.Option(..., "--output", help="输出项目目录"),
) -> None:
    """生成项目 Manifest 模板（复制 templates/manifest.yaml 并改写 project/domain/city）。"""
    tmpl = TEMPLATES_DIR / "manifest.yaml"
    if not tmpl.is_file():
        typer.echo(f"模板缺失: {tmpl}", err=True)
        raise typer.Exit(1)
    import yaml

    data = yaml.safe_load(tmpl.read_text(encoding="utf-8"))
    data["project"] = f"{city}-{domain}"
    data["domain"] = domain
    data["city"] = city
    output.mkdir(parents=True, exist_ok=True)
    target = output / "manifest.yaml"
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    typer.echo(f"已生成 {target}")
    typer.echo("下一步: toolbox manifest validate --manifest <path>/manifest.yaml")


@app.command("manifest-validate")
def manifest_validate(
    manifest: Path = typer.Option(..., "--manifest", help="manifest.yaml 路径"),
) -> None:
    """校验 Manifest（project_id 正则 + schema 分档 + manifest.schema.json）。"""
    try:
        m = load_manifest(manifest)
    except Exception as exc:
        typer.echo(f"FAIL: {exc}", err=True)
        raise typer.Exit(1) from exc
    errors = validate_manifest(m.raw, _load_manifest_schema())
    if errors:
        for e in errors:
            typer.echo(f"FAIL: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"PASS: {m.project_id} (schemaVersion={m.raw.get('schemaVersion')})")


@schema_app.command("list")
def schema_list() -> None:
    """列出数据契约与版本。"""
    for name in SCHEMA_NAMES:
        schema = load_schema(name)
        typer.echo(f"{name}\t{Path(name + '.schema.json')}  v{schema.get('version', '?')}")


@schema_app.command("validate")
def schema_validate(
    schema: str = typer.Option(..., "--schema", help="raw/clean/scored/audit"),
    data: Path = typer.Option(..., "--data", help="待校验 JSON 文件"),
) -> None:
    """按契约校验一层数据。"""
    if schema not in ("raw", "clean", "scored", "audit"):
        typer.echo(f"FAIL: --schema 必须是 raw/clean/scored/audit", err=True)
        raise typer.Exit(1)
    try:
        record = json.loads(data.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        typer.echo(f"FAIL: 数据文件不可读 {data}: {exc}", err=True)
        raise typer.Exit(1) from exc
    errors = validate_data(schema, record)
    if errors:
        for e in errors:
            typer.echo(f"FAIL: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"PASS: {data} 符合 {schema}.schema.json")


@ontology_app.command("verify")
def ontology_verify(
    pack: Path = typer.Option(..., "--pack", help="本体包目录（含 pack.yaml）"),
) -> None:
    """校验本体包：pack.yaml 契约 + 六件套存在 + YAML/JSON 可解析。"""
    errors = verify_pack(pack)
    if errors:
        for e in errors:
            typer.echo(f"FAIL: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"PASS: {pack} 本体包合法")


@ontology_app.command("install")
def ontology_install(
    pack: Path = typer.Option(..., "--pack", help="本体包目录"),
    ledger: Path = typer.Option(DEFAULT_LEDGER, "--ledger", help="包注册表 ledger 路径"),
) -> None:
    """登记本体包到 ledger（幂等：同 name@version 拒绝重复）。"""
    try:
        entry = install_pack(pack, ledger)
    except Exception as exc:
        typer.echo(f"FAIL: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"INSTALLED: {entry.name}@{entry.version} sha256={entry.sha256} ledger={ledger}"
    )


@ontology_app.command("list")
def ontology_list(
    ledger: Path = typer.Option(DEFAULT_LEDGER, "--ledger", help="包注册表 ledger 路径"),
) -> None:
    """列出已安装本体包。"""
    try:
        records = list_packs(ledger)
    except Exception as exc:
        typer.echo(f"FAIL: {exc}", err=True)
        raise typer.Exit(1) from exc
    if not records:
        typer.echo("(空)")
        return
    for r in records:
        typer.echo(f"{r['name']}@{r['version']}\tsha256={r['sha256']}\t{r['installed_at']}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())

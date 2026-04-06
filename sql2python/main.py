#!/usr/bin/env python3
"""
SQL2Python - MS SQL Stored Procedure → Python 변환기
Ollama 3-way 비교 (모델 태그는 config.yaml 의 gemma/qwen/glm.model_name).

사용법:
    python main.py convert --backend gemma --input examples/sql/usp_add_authorbook_storebook.sql
    python main.py convert --backend qwen  --input examples/sql/usp_add_authorbook_storebook.sql
    python main.py convert --backend glm   --input examples/sql/usp_add_authorbook_storebook.sql
    python main.py compare --input examples/sql/usp_add_authorbook_storebook.sql
    python main.py batch   --input-dir examples/sql/ --output-dir output/
    python main.py preview --input examples/sql/usp_add_authorbook_storebook.sql --backend gemma
"""
from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))

from prompts.few_shot_examples import ALL_EXAMPLES, FEW_SHOT_COUNT
from prompts.template import build_gemma_prompt
from converters.comparator import Comparator

console = Console()


def _clamp_num_examples(n: int) -> int:
    """퓨샷 개수를 0..len(ALL_EXAMPLES) 으로 제한 (목록이 비면 0)."""
    m = len(ALL_EXAMPLES)
    if m == 0:
        return 0
    return max(1, min(int(n), m))


_NUM_EXAMPLES_HELP = (
    "퓨샷 예시 수 (few_shot_examples.yaml 전체 사용이 기본; "
    f"1~{FEW_SHOT_COUNT} 로 줄일 수 있음)"
    if FEW_SHOT_COUNT > 0
    else "퓨샷 예시 수 (examples 가 비어 있으면 0)"
)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _ollama_convert_kwargs(cfg: dict, backend: str) -> dict:
    g = cfg[backend]
    return {
        "temperature": g["temperature"],
        "top_p": g.get("top_p", 0.9),
        "max_new_tokens": g["max_new_tokens"],
        "repetition_penalty": g.get("repetition_penalty", 1.1),
    }


def _make_converter(cfg: dict, backend: str):
    from converters.ollama_converter import OllamaConverter
    host = cfg.get("ollama", {}).get("host", "http://localhost:11434")
    return OllamaConverter(
        model_name=cfg[backend]["model_name"],
        host=host,
    )


# ═══════════════════════════════════════
#  CLI
# ═══════════════════════════════════════
@click.group()
def cli():
    """SQL2Python: MS SQL Procedure → Python (Ollama, config.yaml 모델 태그)"""


# ─────────── convert ───────────
@cli.command()
@click.option(
    "--backend",
    type=click.Choice(["gemma", "qwen", "glm"]),
    required=True,
    help="사용할 모델"
)
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option(
    "--num-examples",
    default=FEW_SHOT_COUNT,
    type=int,
    show_default=True,
    help=_NUM_EXAMPLES_HELP,
)
@click.option("--config", "config_path", default="config.yaml")
def convert(backend, input_path, output_dir, num_examples, config_path):
    """SQL 파일을 Python으로 변환합니다."""
    num_examples = _clamp_num_examples(num_examples)
    cfg = load_config(config_path)
    sql_path = Path(input_path)

    if not sql_path.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {sql_path}[/red]")
        return

    console.print(Panel(
        f"[bold]모델:[/bold] {cfg[backend]['model_name']}\n"
        f"[bold]입력:[/bold] {sql_path}\n"
        f"[bold]퓨샷:[/bold] 예 ({num_examples}개)",
        title="SQL → Python 변환",
    ))

    converter = _make_converter(cfg, backend)
    result = converter.convert_file(
        sql_path,
        output_dir=output_dir,
        num_examples=num_examples,
        **_ollama_convert_kwargs(cfg, backend),
    )

    console.print()
    console.print(Syntax(
        result["python_code"], "python",
        theme="monokai", line_numbers=True
    ))
    console.print()

    table = Table(title="변환 결과")
    table.add_column("항목", style="cyan")
    table.add_column("값", style="green")
    table.add_row("모델", result["model"])
    table.add_row("소요 시간", f"{result['elapsed_sec']}초")
    table.add_row("출력 토큰", str(result["output_tokens"]))
    if "output_file" in result:
        table.add_row("저장 위치", result["output_file"])
    console.print(table)


# ─────────── compare ───────────
@cli.command()
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option(
    "--num-examples",
    default=FEW_SHOT_COUNT,
    type=int,
    show_default=True,
    help=_NUM_EXAMPLES_HELP,
)
@click.option("--config", "config_path", default="config.yaml")
@click.option("--plots/--no-plots", default=False, help="output-dir/report 에 비교 차트 PNG 저장")
def compare(input_path, output_dir, num_examples, config_path, plots):
    """gemma / qwen / glm Ollama 백엔드 3-way 비교."""
    num_examples = _clamp_num_examples(num_examples)
    cfg = load_config(config_path)
    sql_path = Path(input_path)

    if not sql_path.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {sql_path}[/red]")
        return

    console.print(Panel(
        f"[bold]gemma[/bold]  {cfg['gemma']['model_name']}\n"
        f"[bold]qwen[/bold]   {cfg['qwen']['model_name']}\n"
        f"[bold]glm[/bold]    {cfg['glm']['model_name']}\n"
        f"입력: {sql_path.name} | 퓨샷: {num_examples}개",
        title="3-Way 비교 모드"
    ))

    results = {}
    for backend, label, color in [
        ("gemma", "Gemma", "yellow"),
        ("qwen",  "Qwen",  "blue"),
        ("glm",   "GLM",   "magenta"),
    ]:
        console.print(f"\n[bold {color}]━━━ {label} 변환 중... ━━━[/bold {color}]")
        converter = _make_converter(cfg, backend)
        results[backend] = converter.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            **_ollama_convert_kwargs(cfg, backend),
        )

    _print_three_way_comparison(
        sql_path.name,
        results["gemma"],
        results["qwen"],
        results["glm"],
        cfg,
    )

    comp = Comparator()
    report_path = comp.generate_report(
        [{"file": str(sql_path),
          "gemma": results["gemma"],
          "qwen":  results["qwen"],
          "glm":   results["glm"]}],
        Path(output_dir) / "comparison_report.json",
        with_plots=plots,
    )
    console.print(f"\n[dim]리포트 저장: {report_path}[/dim]")


# ─────────── batch ───────────
@cli.command()
@click.option("--input-dir", required=True, help="SQL 파일 디렉토리")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option(
    "--num-examples",
    default=FEW_SHOT_COUNT,
    type=int,
    show_default=True,
    help=_NUM_EXAMPLES_HELP,
)
@click.option("--config", "config_path", default="config.yaml")
@click.option("--plots/--no-plots", default=False, help="output-dir/report 에 배치 비교 차트 PNG 저장")
def batch(input_dir, output_dir, num_examples, config_path, plots):
    """폴더 내 전체 SQL을 일괄 변환하고 3-way 비교합니다."""
    num_examples = _clamp_num_examples(num_examples)
    cfg = load_config(config_path)
    sql_dir = Path(input_dir)
    sql_files = sorted(sql_dir.glob("*.sql"))

    if not sql_files:
        console.print(f"[red]{sql_dir} 에 SQL 파일이 없습니다[/red]")
        return

    console.print(Panel(
        f"총 {len(sql_files)}개 SQL 파일\n"
        f"gemma: {cfg['gemma']['model_name']}\n"
        f"qwen:  {cfg['qwen']['model_name']}\n"
        f"glm:   {cfg['glm']['model_name']}",
        title="배치 모드"
    ))

    all_results = []

    for i, sql_path in enumerate(sql_files, 1):
        console.print(f"\n[bold]━━━ [{i}/{len(sql_files)}] {sql_path.name} ━━━[/bold]")

        file_results = {}
        for backend, label, color in [
            ("gemma", "Gemma", "yellow"),
            ("qwen",  "Qwen",  "blue"),
            ("glm",   "GLM",   "magenta"),
        ]:
            console.print(f"[{color}]  {label} 변환 중...[/{color}]")
            converter = _make_converter(cfg, backend)
            file_results[backend] = converter.convert_file(
                sql_path,
                output_dir=output_dir,
                num_examples=num_examples,
                **_ollama_convert_kwargs(cfg, backend),
            )

        all_results.append({
            "file": sql_path.name,
            "gemma": file_results["gemma"],
            "qwen":  file_results["qwen"],
            "glm":   file_results["glm"],
        })
        _print_three_way_comparison(
            sql_path.name,
            file_results["gemma"],
            file_results["qwen"],
            file_results["glm"],
            cfg,
        )

    _print_batch_summary(all_results, cfg)
    comp = Comparator()
    report_path = comp.generate_report(
        all_results,
        Path(output_dir) / "batch_report.json",
        with_plots=plots,
    )
    console.print(f"\n[dim]리포트: {report_path}[/dim]")


# ─────────── analyze ───────────
@cli.command()
@click.option("--input", "input_path", required=True, help="분석할 Python 파일 경로")
@click.option("--sql", "sql_path", default=None, help="원본 SQL 파일 경로 (함수명 보존 여부 확인용, 선택)")
@click.option("--model", "model_label", default="unknown", show_default=True, help="출력에 표시할 모델 이름")
def analyze(input_path, sql_path, model_label):
    """변환된 Python 파일의 코드 품질을 분석합니다 (모델 호출 없이)."""
    py_path = Path(input_path)
    if not py_path.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {py_path}[/red]")
        return

    code = py_path.read_text(encoding="utf-8")

    comp = Comparator()
    score = comp.analyze_code(
        code,
        model=model_label,
        sql_file=sql_path or "",
    )

    console.print(Panel(
        f"[bold]파일:[/bold] {py_path}\n"
        f"[bold]모델:[/bold] {model_label}\n"
        f"[bold]줄 수:[/bold] {score.line_count}",
        title="코드 분석",
    ))

    table = Table(title=f"품질 점수: {score.execution_score} / 100")
    table.add_column("검사 항목", style="cyan", width=30)
    table.add_column("결과", justify="center", width=10)
    table.add_column("배점", justify="right", width=8)

    def _yn(ok: bool) -> str:
        return "[green]✓[/green]" if ok else "[red]✗[/red]"

    table.add_row("Python 구문 유효 (AST)",     _yn(score.syntax_valid),            "+30")
    table.add_row("파라미터화 쿼리 (?)",          _yn(score.parameterized_query),     "+15")
    table.add_row("try/except 포함",             _yn(score.has_try_except),          "+10")
    table.add_row("with pyodbc.connect(...)",    _yn(score.has_with_connect),        "+10")
    table.add_row("commit 포함",                 _yn(score.commit_present),          "+10")
    table.add_row("rollback 포함",               _yn(score.rollback_present),        "+10")
    table.add_row("플레이스홀더 개수 일치",        _yn(score.placeholder_match),       "+10")
    table.add_row("위험 패턴 없음",               _yn(not score.dangerous_pattern_found), "+5")

    if sql_path:
        table.add_row("함수명 보존",              _yn(score.function_name_preserved),  "—")

    console.print(table)

    def _score_color(s: int) -> str:
        if s >= 70:
            return "green"
        if s >= 40:
            return "yellow"
        return "red"

    color = _score_color(score.execution_score)
    console.print(
        f"\n[bold]총점:[/bold] [{color}]{score.execution_score} / 100[/{color}]"
    )


# ─────────── preview ───────────
@cli.command()
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option(
    "--backend",
    type=click.Choice(["gemma", "qwen", "glm"]),
    default="gemma"
)
@click.option(
    "--num-examples",
    default=FEW_SHOT_COUNT,
    type=int,
    show_default=True,
    help=_NUM_EXAMPLES_HELP,
)
@click.option("--config", "config_path", default="config.yaml")
def preview(input_path, backend, num_examples, config_path):
    """생성될 프롬프트를 미리봅니다 (모델 호출 없이)."""
    num_examples = _clamp_num_examples(num_examples)
    cfg = load_config(config_path)
    sql_code = Path(input_path).read_text(encoding="utf-8")
    prompt = build_gemma_prompt(sql_code, num_examples=num_examples)

    model_name = cfg[backend]["model_name"]
    console.print(Panel(
        f"모델: {model_name}\n"
        f"토큰 수 (대략): ~{len(prompt.split()) * 1.3:.0f}",
        title=f"{backend.upper()} 프롬프트 미리보기"
    ))
    console.print(Syntax(prompt, "text", theme="monokai", word_wrap=True))


# ═══════════════════════════════════════
#  출력 헬퍼
# ═══════════════════════════════════════
def _print_three_way_comparison(
    filename,
    gemma_result,
    qwen_result,
    glm_result,
    cfg: dict,
):
    table = Table(title=f"비교 결과: {filename}")
    table.add_column("항목", style="cyan", width=18)
    table.add_column("Gemma", style="yellow", justify="left", overflow="fold")
    table.add_column("Qwen", style="blue", justify="left", overflow="fold")
    table.add_column("GLM", style="magenta", justify="left", overflow="fold")

    table.add_row(
        "Ollama model_name",
        gemma_result.get("model", cfg["gemma"]["model_name"]),
        qwen_result.get("model", cfg["qwen"]["model_name"]),
        glm_result.get("model", cfg["glm"]["model_name"]),
    )
    table.add_row(
        "소요 시간",
        f"{gemma_result['elapsed_sec']}초",
        f"{qwen_result['elapsed_sec']}초",
        f"{glm_result['elapsed_sec']}초",
    )
    table.add_row(
        "출력 토큰",
        str(gemma_result["output_tokens"]),
        str(qwen_result["output_tokens"]),
        str(glm_result["output_tokens"]),
    )
    table.add_row(
        "퓨샷 예시 수",
        str(gemma_result.get("few_shot", "-")),
        str(qwen_result.get("few_shot", "-")),
        str(glm_result.get("few_shot", "-")),
    )
    table.add_row("비용", "무료", "무료", "무료")
    console.print(table)


def _print_batch_summary(results, cfg: dict):
    console.print("\n")
    table = Table(title="배치 처리 요약")
    table.add_column("Ollama 태그", style="cyan", overflow="fold")
    table.add_column("평균 소요 시간", justify="center")
    table.add_column("평균 출력 토큰", justify="center")

    for label, key in [
        (cfg["gemma"]["model_name"], "gemma"),
        (cfg["qwen"]["model_name"], "qwen"),
        (cfg["glm"]["model_name"], "glm"),
    ]:
        times  = [r[key]["elapsed_sec"]   for r in results if key in r]
        tokens = [r[key]["output_tokens"] for r in results if key in r]
        avg_time  = sum(times)  / len(times)  if times  else 0
        avg_token = sum(tokens) / len(tokens) if tokens else 0
        table.add_row(label, f"{avg_time:.1f}초", f"{avg_token:.0f}")

    console.print(table)


if __name__ == "__main__":
    cli()
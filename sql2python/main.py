#!/usr/bin/env python3
"""
SQL2Python - MS SQL Stored Procedure → Python 변환기
Gemma (퓨샷) + GPT 비교 도구

사용법:
    # Gemma로 단일 파일 변환 (기본: 퓨샷 프롬프트)
    python main.py convert --backend gemma --input examples/sql/sample1.sql

    # GPT로 변환 (기본: 퓨샷, 옵션으로 제로샷 가능)
    python main.py convert --backend gpt --input examples/sql/sample1.sql          # 퓨샷
    python main.py convert --backend gpt --zero-shot --input examples/sql/sample1.sql  # 제로샷

    # Gemma vs GPT 비교
    python main.py compare --input examples/sql/sample1.sql

    # 폴더 내 전체 SQL 일괄 변환 + 비교
    python main.py batch --input-dir examples/sql/ --output-dir output/

    # 프롬프트만 미리보기
    python main.py preview --input examples/sql/sample1.sql --backend gemma
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

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from prompts.template import build_gemma_prompt, build_gpt_messages
from converters.comparator import Comparator

console = Console()


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _gemma_convert_kwargs(cfg: dict) -> dict:
    """config의 생성 옵션을 Gemma convert에 넘길 인자로 정리합니다."""
    g = cfg["gemma"]
    return {
        "temperature": g["temperature"],
        "top_p": g.get("top_p", 0.9),
        "max_new_tokens": g["max_new_tokens"],
        "repetition_penalty": g.get("repetition_penalty", 1.1),
    }


def _gpt_convert_kwargs(cfg: dict) -> dict:
    """config의 생성 옵션을 GPT convert에 넘길 인자로 정리합니다."""
    g = cfg["gpt"]
    return {
        "temperature": g["temperature"],
        "top_p": g.get("top_p", 0.9),
        "max_tokens": g["max_tokens"],
    }


# ═══════════════════════════════════════
#  CLI
# ═══════════════════════════════════════
@click.group()
def cli():
    """SQL2Python: MS SQL Procedure → Python 변환기 (Gemma 퓨샷 + GPT 비교)"""
    pass


# ─────────── convert ───────────
@cli.command()
@click.option("--backend", type=click.Choice(["gemma", "gpt"]), required=True, help="사용할 모델")
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option("--few-shot/--zero-shot", default=True, help="퓨샷 사용 여부 (GPT만)")
@click.option("--num-examples", default=3, help="퓨샷 예시 수 (1~5)")
@click.option("--config", "config_path", default="config.yaml", help="설정 파일")
def convert(backend, input_path, output_dir, few_shot, num_examples, config_path):
    """SQL 파일을 Python으로 변환합니다."""
    cfg = load_config(config_path)
    sql_path = Path(input_path)

    if not sql_path.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {sql_path}[/red]")
        return

    console.print(Panel(
        f"[bold]모델:[/bold] {backend}\n"
        f"[bold]입력:[/bold] {sql_path}\n"
        f"[bold]퓨샷:[/bold] {'예' if few_shot else '아니오'} ({num_examples}개)",
        title="SQL → Python 변환",
    ))

    if backend == "gemma":
        from converters.gemma_converter import GemmaConverter
        gcfg = cfg["gemma"]
        converter = GemmaConverter(
            model_name=gcfg["model_name"],
            load_in_4bit=gcfg.get("load_in_4bit", True),
            load_in_8bit=gcfg.get("load_in_8bit", False),
        )
        result = converter.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            **_gemma_convert_kwargs(cfg),
        )
    else:
        from converters.gpt_converter import GPTConverter
        gcfg = cfg["gpt"]
        converter = GPTConverter(model_name=gcfg["model_name"])
        result = converter.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            use_few_shot=few_shot,
            **_gpt_convert_kwargs(cfg),
        )

    # 결과 출력
    console.print()
    console.print(Syntax(result["python_code"], "python", theme="monokai", line_numbers=True))
    console.print()

    table = Table(title="변환 결과")
    table.add_column("항목", style="cyan")
    table.add_column("값", style="green")
    table.add_row("모델", result["model"])
    table.add_row("소요 시간", f"{result['elapsed_sec']}초")
    table.add_row("입력 토큰", str(result["input_tokens"]))
    table.add_row("출력 토큰", str(result["output_tokens"]))
    if "cost_usd" in result:
        table.add_row("비용", f"${result['cost_usd']:.4f}")
    if "output_file" in result:
        table.add_row("저장 위치", result["output_file"])
    console.print(table)


# ─────────── compare ───────────
@cli.command()
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option("--num-examples", default=3, help="퓨샷 예시 수")
@click.option("--config", "config_path", default="config.yaml")
@click.option(
    "--include-zero-shot/--few-shot-only",
    default=False,
    help="GPT 제로샷도 함께 실행해 3-way 비교할지 여부 (기본: Gemma vs GPT 퓨샷만 비교)",
)
def compare(input_path, output_dir, num_examples, config_path, include_zero_shot):
    """Gemma vs GPT 변환 결과를 비교합니다 (기본: 둘 다 퓨샷)."""
    cfg = load_config(config_path)
    sql_path = Path(input_path)

    if not sql_path.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {sql_path}[/red]")
        return

    console.print(Panel("Gemma vs GPT 비교 변환을 시작합니다", title="비교 모드"))

    # 1) Gemma 변환
    console.print("\n[bold yellow]━━━ Gemma (퓨샷) 변환 중... ━━━[/bold yellow]")
    from converters.gemma_converter import GemmaConverter
    gemma = GemmaConverter(
        model_name=cfg["gemma"]["model_name"],
        load_in_4bit=cfg["gemma"].get("load_in_4bit", True),
        load_in_8bit=cfg["gemma"].get("load_in_8bit", False),
    )
    gemma_result = gemma.convert_file(
        sql_path,
        output_dir=output_dir,
        num_examples=num_examples,
        **_gemma_convert_kwargs(cfg),
    )

    # 2) GPT 퓨샷 변환
    console.print("\n[bold blue]━━━ GPT (퓨샷) 변환 중... ━━━[/bold blue]")
    from converters.gpt_converter import GPTConverter
    gpt = GPTConverter(model_name=cfg["gpt"]["model_name"])
    gpt_fs_result = gpt.convert_file(
        sql_path,
        output_dir=output_dir,
        num_examples=num_examples,
        use_few_shot=True,
        **_gpt_convert_kwargs(cfg),
    )

    gpt_zs_result = None
    if include_zero_shot:
        # 3) GPT 제로샷 변환
        console.print("\n[bold magenta]━━━ GPT (제로샷) 변환 중... ━━━[/bold magenta]")
        gpt_zs_result = gpt.convert_file(
            sql_path,
            output_dir=output_dir,
            use_few_shot=False,
            **_gpt_convert_kwargs(cfg),
        )

    # 4) 비교 분석
    comp = Comparator()
    result = comp.compare(
        sql_file=str(sql_path),
        gemma_result=gemma_result,
        gpt_result=gpt_fs_result,
        gpt_zeroshot_result=gpt_zs_result,
    )

    # 결과 테이블 출력
    _print_comparison_table(result)

    # JSON 리포트 저장
    report_path = comp.generate_report([result], Path(output_dir) / "comparison_report.json")
    console.print(f"\n[dim]리포트 저장: {report_path}[/dim]")


# ─────────── batch ───────────
@cli.command()
@click.option("--input-dir", required=True, help="SQL 파일 디렉토리")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option("--num-examples", default=3)
@click.option("--config", "config_path", default="config.yaml")
@click.option(
    "--include-zero-shot/--few-shot-only",
    default=False,
    help="배치에서도 GPT 제로샷을 함께 실행할지 여부 (기본: Gemma vs GPT 퓨샷만)",
)
def batch(input_dir, output_dir, num_examples, config_path, include_zero_shot):
    """폴더 내 전체 SQL을 일괄 변환하고 비교합니다."""
    cfg = load_config(config_path)
    sql_dir = Path(input_dir)
    sql_files = sorted(sql_dir.glob("*.sql"))

    if not sql_files:
        console.print(f"[red]{sql_dir} 에 SQL 파일이 없습니다[/red]")
        return

    console.print(Panel(f"총 {len(sql_files)}개 SQL 파일 일괄 변환", title="배치 모드"))

    # 모델 초기화
    from converters.gemma_converter import GemmaConverter
    from converters.gpt_converter import GPTConverter

    gemma = GemmaConverter(
        model_name=cfg["gemma"]["model_name"],
        load_in_4bit=cfg["gemma"].get("load_in_4bit", True),
        load_in_8bit=cfg["gemma"].get("load_in_8bit", False),
    )
    gpt = GPTConverter(model_name=cfg["gpt"]["model_name"])
    comp = Comparator()
    results = []

    for i, sql_path in enumerate(sql_files, 1):
        console.print(f"\n[bold]━━━ [{i}/{len(sql_files)}] {sql_path.name} ━━━[/bold]")

        gemma_result = gemma.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            **_gemma_convert_kwargs(cfg),
        )
        gpt_fs_result = gpt.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            **_gpt_convert_kwargs(cfg),
        )
        gpt_zs_result = None
        if include_zero_shot:
            gpt_zs_result = gpt.convert_file(
                sql_path,
                output_dir=output_dir,
                use_few_shot=False,
                **_gpt_convert_kwargs(cfg),
            )

        comparison = comp.compare(
            sql_file=str(sql_path),
            gemma_result=gemma_result,
            gpt_result=gpt_fs_result,
            gpt_zeroshot_result=gpt_zs_result,
        )
        results.append(comparison)
        _print_comparison_table(comparison)

    # 최종 요약
    report_path = comp.generate_report(results, Path(output_dir) / "batch_comparison_report.json")
    _print_batch_summary(results)
    console.print(f"\n[dim]리포트: {report_path}[/dim]")


# ─────────── preview ───────────
@cli.command()
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option("--backend", type=click.Choice(["gemma", "gpt"]), default="gemma")
@click.option("--num-examples", default=3)
@click.option(
    "--max-chars",
    default=0,
    type=int,
    show_default=True,
    help="GPT 미리보기에서 각 메시지당 최대 출력 문자 수 (0이면 제한 없음)",
)
def preview(input_path, backend, num_examples, max_chars):
    """생성될 프롬프트를 미리봅니다 (모델 호출 없이)."""
    sql_code = Path(input_path).read_text(encoding="utf-8")

    if backend == "gemma":
        prompt = build_gemma_prompt(sql_code, num_examples=num_examples)
        console.print(Panel(f"토큰 수 (대략): ~{len(prompt.split()) * 1.3:.0f}", title="Gemma 프롬프트 미리보기"))
        console.print(Syntax(prompt, "text", theme="monokai", word_wrap=True))
    else:
        messages = build_gpt_messages(sql_code, num_examples=num_examples)
        console.print(Panel(f"메시지 수: {len(messages)}", title="GPT 프롬프트 미리보기"))
        for msg in messages:
            role_color = {"system": "red", "user": "green", "assistant": "blue"}.get(msg["role"], "white")
            content = msg.get("content", "") or ""
            truncated = False
            if max_chars and len(content) > max_chars:
                content = content[:max_chars]
                truncated = True

            console.print(f"\n[bold {role_color}]── {msg['role'].upper()} ──[/bold {role_color}]")
            console.print(Syntax(content, "text", theme="monokai", word_wrap=True))
            if truncated:
                console.print(f"[dim](출력 제한으로 일부가 생략되었습니다: --max-chars {max_chars})[/dim]")


# ═══════════════════════════════════════
#  출력 헬퍼
# ═══════════════════════════════════════
def _print_comparison_table(result):
    """비교 결과를 테이블로 출력합니다."""
    table = Table(title=f"비교 결과: {Path(result.sql_file).name}")
    table.add_column("항목", style="cyan", width=22)
    table.add_column("Gemma (퓨샷)", style="yellow", justify="center")
    table.add_column("GPT (퓨샷)", style="blue", justify="center")
    table.add_column("GPT (제로샷)", style="magenta", justify="center")

    def _row(label, gemma_val, gpt_val, gpt_zs_val):
        table.add_row(label, str(gemma_val), str(gpt_val), str(gpt_zs_val))

    g = result.gemma_score
    gf = result.gpt_score
    gz = result.gpt_zeroshot_score

    _row("구문 유효", _check(g and g.syntax_valid), _check(gf and gf.syntax_valid), _check(gz and gz.syntax_valid))
    _row("타입힌트", _check(g and g.has_type_hints), _check(gf and gf.has_type_hints), _check(gz and gz.has_type_hints))
    _row("Docstring", _check(g and g.has_docstring), _check(gf and gf.has_docstring), _check(gz and gz.has_docstring))
    _row("파라미터 바인딩", _check(g and g.uses_parameterized_query), _check(gf and gf.uses_parameterized_query), _check(gz and gz.uses_parameterized_query))
    _row("에러 처리", _check(g and g.has_error_handling), _check(gf and gf.has_error_handling), _check(gz and gz.has_error_handling))
    _row("Context Manager", _check(g and g.has_context_manager), _check(gf and gf.has_context_manager), _check(gz and gz.has_context_manager))
    _row("코드 줄 수", g.line_count if g else "-", gf.line_count if gf else "-", gz.line_count if gz else "-")
    _row("소요 시간 (초)", g.elapsed_sec if g else "-", gf.elapsed_sec if gf else "-", gz.elapsed_sec if gz else "-")
    _row("비용 ($)", "무료", f"${gf.cost_usd:.4f}" if gf else "-", f"${gz.cost_usd:.4f}" if gz else "-")
    _row(
        "품질 점수",
        f"[bold]{g.quality_score}/100[/bold]" if g else "-",
        f"[bold]{gf.quality_score}/100[/bold]" if gf else "-",
        f"[bold]{gz.quality_score}/100[/bold]" if gz else "-",
    )

    console.print(table)
    if result.winner:
        console.print(f"  [bold green]승자: {result.winner}[/bold green]")


def _print_batch_summary(results):
    """배치 비교 요약을 출력합니다."""
    console.print("\n")
    table = Table(title="배치 비교 요약")
    table.add_column("모델", style="cyan")
    table.add_column("승리 횟수", justify="center")
    table.add_column("평균 점수", justify="center")

    for label, key in [("Gemma 퓨샷", "gemma"), ("GPT 퓨샷", "gpt_fewshot"), ("GPT 제로샷", "gpt_zeroshot")]:
        wins = sum(1 for r in results if r.winner == key)
        scores = []
        for r in results:
            s = getattr(r, f"{key}_score", None) or (r.gpt_score if key == "gpt_fewshot" else None)
            if key == "gemma":
                s = r.gemma_score
            elif key == "gpt_fewshot":
                s = r.gpt_score
            elif key == "gpt_zeroshot":
                s = r.gpt_zeroshot_score
            if s:
                scores.append(s.quality_score)
        avg = sum(scores) / len(scores) if scores else 0
        table.add_row(label, str(wins), f"{avg:.1f}/100")

    console.print(table)


def _check(val: bool) -> str:
    return "[green]O[/green]" if val else "[red]X[/red]"


if __name__ == "__main__":
    cli()

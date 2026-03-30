#!/usr/bin/env python3
"""
SQL2Python - MS SQL Stored Procedure → Python 변환기
Gemma 3 12B / Qwen2.5-Coder 14B / GLM-4.5-Air 12B 비교 도구

사용법:
    # 단일 파일 변환
    python main.py convert --backend gemma --input examples/sql/usp_modified_book_storebook.sql
    python main.py convert --backend qwen  --input examples/sql/usp_modified_book_storebook.sql
    python main.py convert --backend glm   --input examples/sql/usp_modified_book_storebook.sql

    # 3개 모델 비교
    python main.py compare --input examples/sql/usp_modified_book_storebook.sql

    # 폴더 전체 일괄 변환 + 비교
    python main.py batch --input-dir examples/sql/ --output-dir output/

    # 프롬프트 미리보기
    python main.py preview --input examples/sql/usp_modified_book_storebook.sql --backend gemma
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
except Exception:
    load_dotenv = None

sys.path.insert(0, str(Path(__file__).parent))

from prompts.template import build_gemma_prompt
from converters.comparator import Comparator

console = Console()


def load_config(path: str = "config.yaml") -> dict:
    """설정 파일을 로드합니다. 상대 경로는 항상 main.py가 있는 디렉터리 기준입니다."""
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _gemma_convert_kwargs(cfg: dict) -> dict:
    g = cfg["gemma"]
    return {
        "temperature": g["temperature"],
        "top_p": g.get("top_p", 0.9),
        "max_new_tokens": g["max_new_tokens"],
        "repetition_penalty": g.get("repetition_penalty", 1.1),
    }


def _qwen_convert_kwargs(cfg: dict) -> dict:
    q = cfg["qwen"]
    return {
        "temperature": q["temperature"],
        "top_p": q.get("top_p", 0.9),
        "max_new_tokens": q["max_new_tokens"],
        "repetition_penalty": q.get("repetition_penalty", 1.1),
    }


def _glm_convert_kwargs(cfg: dict) -> dict:
    g = cfg["glm"]
    return {
        "temperature": g["temperature"],
        "top_p": g.get("top_p", 0.9),
        "max_new_tokens": g["max_new_tokens"],
        "repetition_penalty": g.get("repetition_penalty", 1.1),
    }


# ═══════════════════════════════════════
#  CLI
# ═══════════════════════════════════════
@click.group()
def cli():
    """SQL2Python: MS SQL Procedure → Python 변환기 (Gemma / Qwen / GLM 비교)"""
    if load_dotenv is not None:
        load_dotenv(override=False)


# ─────────── convert ───────────
@cli.command()
@click.option(
    "--backend",
    type=click.Choice(["gemma", "qwen", "glm"]),
    required=True,
    help="사용할 모델",
)
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option("--num-examples", default=3, help="퓨샷 예시 수 (1~10)")
@click.option("--config", "config_path", default="config.yaml", help="설정 파일")
def convert(backend, input_path, output_dir, num_examples, config_path):
    """SQL 파일을 Python으로 변환합니다."""
    cfg = load_config(config_path)
    sql_path = Path(input_path)

    if not sql_path.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {sql_path}[/red]")
        return

    console.print(
        Panel(
            f"[bold]모델:[/bold] {backend}\n"
            f"[bold]입력:[/bold] {sql_path}\n"
            f"[bold]퓨샷:[/bold] 예 ({num_examples}개)",
            title="SQL → Python 변환",
        )
    )

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

    elif backend == "qwen":
        from converters.qwen_converter import QwenConverter

        qcfg = cfg["qwen"]
        converter = QwenConverter(
            model_name=qcfg["model_name"],
            load_in_4bit=qcfg.get("load_in_4bit", True),
            load_in_8bit=qcfg.get("load_in_8bit", False),
        )
        result = converter.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            **_qwen_convert_kwargs(cfg),
        )

    elif backend == "glm":
        from converters.glm_converter import GLMConverter

        gcfg = cfg["glm"]
        converter = GLMConverter(
            model_name=gcfg["model_name"],
            load_in_4bit=gcfg.get("load_in_4bit", True),
            load_in_8bit=gcfg.get("load_in_8bit", False),
        )
        result = converter.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            **_glm_convert_kwargs(cfg),
        )

    console.print()
    console.print(
        Syntax(
            result["python_code"],
            "python",
            theme="monokai",
            line_numbers=True,
        )
    )
    console.print()

    table = Table(title="변환 결과")
    table.add_column("항목", style="cyan")
    table.add_column("값", style="green")
    table.add_row("모델", result["model"])
    table.add_row("소요 시간", f"{result['elapsed_sec']}초")
    table.add_row("입력 토큰", str(result["input_tokens"]))
    table.add_row("출력 토큰", str(result["output_tokens"]))
    if "output_file" in result:
        table.add_row("저장 위치", result["output_file"])
    console.print(table)


# ─────────── compare ───────────
@cli.command()
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option("--num-examples", default=3, help="퓨샷 예시 수")
@click.option("--config", "config_path", default="config.yaml")
def compare(input_path, output_dir, num_examples, config_path):
    """Gemma vs Qwen vs GLM 변환 결과를 3-way 비교합니다."""
    cfg = load_config(config_path)
    sql_path = Path(input_path)

    if not sql_path.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {sql_path}[/red]")
        return

    console.print(
        Panel(
            "Gemma 3 12B  vs  Qwen2.5-Coder 14B  vs  GLM-4.5-Air 12B",
            title="3-Way 비교 모드",
        )
    )

    console.print("\n[bold yellow]━━━ Gemma 3 12B (퓨샷) 변환 중... ━━━[/bold yellow]")
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
    gemma.unload_model()

    console.print("\n[bold blue]━━━ Qwen2.5-Coder 14B (퓨샷) 변환 중... ━━━[/bold blue]")
    from converters.qwen_converter import QwenConverter

    qwen = QwenConverter(
        model_name=cfg["qwen"]["model_name"],
        load_in_4bit=cfg["qwen"].get("load_in_4bit", True),
        load_in_8bit=cfg["qwen"].get("load_in_8bit", False),
    )
    qwen_result = qwen.convert_file(
        sql_path,
        output_dir=output_dir,
        num_examples=num_examples,
        **_qwen_convert_kwargs(cfg),
    )
    qwen.unload_model()

    console.print("\n[bold magenta]━━━ GLM-4.5-Air 12B (퓨샷) 변환 중... ━━━[/bold magenta]")
    from converters.glm_converter import GLMConverter

    glm = GLMConverter(
        model_name=cfg["glm"]["model_name"],
        load_in_4bit=cfg["glm"].get("load_in_4bit", True),
        load_in_8bit=cfg["glm"].get("load_in_8bit", False),
    )
    glm_result = glm.convert_file(
        sql_path,
        output_dir=output_dir,
        num_examples=num_examples,
        **_glm_convert_kwargs(cfg),
    )
    glm.unload_model()

    _print_three_way_comparison(sql_path.name, gemma_result, qwen_result, glm_result)

    report_path = Comparator.generate_three_way_hf_report(
        [
            {
                "file": str(sql_path),
                "gemma": gemma_result,
                "qwen": qwen_result,
                "glm": glm_result,
            }
        ],
        Path(output_dir) / "comparison_report.json",
    )
    console.print(f"\n[dim]리포트 저장: {report_path}[/dim]")


# ─────────── batch ───────────
@cli.command()
@click.option("--input-dir", required=True, help="SQL 파일 디렉토리")
@click.option("--output-dir", default="./output", help="출력 디렉토리")
@click.option("--num-examples", default=3)
@click.option("--config", "config_path", default="config.yaml")
def batch(input_dir, output_dir, num_examples, config_path):
    """폴더 내 전체 SQL을 일괄 변환하고 3-way 비교합니다."""
    cfg = load_config(config_path)
    sql_dir = Path(input_dir)
    sql_files = sorted(sql_dir.glob("*.sql"))

    if not sql_files:
        console.print(f"[red]{sql_dir} 에 SQL 파일이 없습니다[/red]")
        return

    console.print(
        Panel(
            f"총 {len(sql_files)}개 SQL 파일 일괄 변환\n"
            f"Gemma 3 12B  vs  Qwen2.5-Coder 14B  vs  GLM-4.5-Air 12B",
            title="배치 모드",
        )
    )

    from converters.gemma_converter import GemmaConverter
    from converters.glm_converter import GLMConverter
    from converters.qwen_converter import QwenConverter

    results = []

    for i, sql_path in enumerate(sql_files, 1):
        console.print(f"\n[bold]━━━ [{i}/{len(sql_files)}] {sql_path.name} ━━━[/bold]")

        console.print("[yellow]  Gemma 변환 중...[/yellow]")
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
        gemma.unload_model()

        console.print("[blue]  Qwen 변환 중...[/blue]")
        qwen = QwenConverter(
            model_name=cfg["qwen"]["model_name"],
            load_in_4bit=cfg["qwen"].get("load_in_4bit", True),
            load_in_8bit=cfg["qwen"].get("load_in_8bit", False),
        )
        qwen_result = qwen.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            **_qwen_convert_kwargs(cfg),
        )
        qwen.unload_model()

        console.print("[magenta]  GLM 변환 중...[/magenta]")
        glm = GLMConverter(
            model_name=cfg["glm"]["model_name"],
            load_in_4bit=cfg["glm"].get("load_in_4bit", True),
            load_in_8bit=cfg["glm"].get("load_in_8bit", False),
        )
        glm_result = glm.convert_file(
            sql_path,
            output_dir=output_dir,
            num_examples=num_examples,
            **_glm_convert_kwargs(cfg),
        )
        glm.unload_model()

        row = {
            "file": sql_path.name,
            "gemma": gemma_result,
            "qwen": qwen_result,
            "glm": glm_result,
        }
        results.append(row)
        _print_three_way_comparison(sql_path.name, gemma_result, qwen_result, glm_result)

    _print_batch_summary(results)
    report_path = Comparator.generate_three_way_hf_report(
        results,
        Path(output_dir) / "batch_report.json",
    )
    console.print(f"\n[dim]리포트: {report_path}[/dim]")


# ─────────── preview ───────────
@cli.command()
@click.option("--input", "input_path", required=True, help="SQL 파일 경로")
@click.option(
    "--backend",
    type=click.Choice(["gemma", "qwen", "glm"]),
    default="gemma",
)
@click.option("--num-examples", default=3)
def preview(input_path, backend, num_examples):
    """생성될 프롬프트를 미리봅니다 (모델 호출 없이)."""
    sql_code = Path(input_path).read_text(encoding="utf-8")
    prompt = build_gemma_prompt(sql_code, num_examples=num_examples)

    title_map = {
        "gemma": "Gemma 프롬프트 미리보기",
        "qwen": "Qwen 프롬프트 미리보기",
        "glm": "GLM 프롬프트 미리보기",
    }
    console.print(
        Panel(
            f"토큰 수 (대략): ~{len(prompt.split()) * 1.3:.0f}",
            title=title_map[backend],
        )
    )
    console.print(Syntax(prompt, "text", theme="monokai", word_wrap=True))


# ═══════════════════════════════════════
#  출력 헬퍼
# ═══════════════════════════════════════
def _print_three_way_comparison(filename, gemma_result, qwen_result, glm_result):
    """3개 모델 비교 결과를 테이블로 출력합니다."""
    table = Table(title=f"비교 결과: {filename}")
    table.add_column("항목", style="cyan", width=20)
    table.add_column("Gemma 3 12B", style="yellow", justify="center")
    table.add_column("Qwen2.5-Coder 14B", style="blue", justify="center")
    table.add_column("GLM-4.5-Air 12B", style="magenta", justify="center")

    table.add_row(
        "소요 시간",
        f"{gemma_result['elapsed_sec']}초",
        f"{qwen_result['elapsed_sec']}초",
        f"{glm_result['elapsed_sec']}초",
    )
    table.add_row(
        "입력 토큰",
        str(gemma_result["input_tokens"]),
        str(qwen_result["input_tokens"]),
        str(glm_result["input_tokens"]),
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


def _print_batch_summary(results):
    """배치 처리 최종 요약을 출력합니다."""
    console.print("\n")
    table = Table(title="배치 처리 요약")
    table.add_column("모델", style="cyan")
    table.add_column("평균 소요 시간", justify="center")
    table.add_column("평균 입력 토큰", justify="center")
    table.add_column("평균 출력 토큰", justify="center")

    for label, key in [
        ("Gemma 3 12B", "gemma"),
        ("Qwen2.5-Coder 14B", "qwen"),
        ("GLM-4.5-Air 12B", "glm"),
    ]:
        times = [r[key]["elapsed_sec"] for r in results if key in r]
        in_tok = [r[key]["input_tokens"] for r in results if key in r]
        out_tok = [r[key]["output_tokens"] for r in results if key in r]

        avg_time = sum(times) / len(times) if times else 0
        avg_in_tok = sum(in_tok) / len(in_tok) if in_tok else 0
        avg_out_tok = sum(out_tok) / len(out_tok) if out_tok else 0

        table.add_row(
            label,
            f"{avg_time:.1f}초",
            f"{avg_in_tok:.0f}",
            f"{avg_out_tok:.0f}",
        )

    console.print(table)


if __name__ == "__main__":
    cli()

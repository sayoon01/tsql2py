"""
퓨샷 프롬프트 템플릿 빌더
Gemma / GPT 각각에 맞는 프롬프트를 생성합니다.
"""
from __future__ import annotations

from .few_shot_examples import ALL_EXAMPLES

# ─────────── 시스템 지침 (공통) ───────────
SYSTEM_INSTRUCTION = """\
당신은 MS SQL Server 저장 프로시저를 Python 코드로 변환하는 전문가입니다.

변환 규칙:
1. DECLARE 변수       → Python 함수 파라미터 (타입힌트 포함)
2. SELECT INTO #temp  → pandas DataFrame
3. CURSOR / WHILE     → pandas 벡터 연산 또는 리스트 컴프리헨션
4. TRY...CATCH        → try...except 블록
5. EXEC / sp_executesql → cursor.execute() (파라미터 바인딩 필수)
6. OUTPUT 파라미터     → 함수 return 값 또는 dataclass
7. BEGIN TRAN / COMMIT → conn.commit() / conn.rollback()
8. MERGE              → SELECT 존재 여부 확인 후 INSERT 또는 UPDATE
9. SET NOCOUNT ON     → 생략 (Python에는 불필요)
10. @@ROWCOUNT        → cursor.rowcount

추가 요구사항:
- pyodbc 사용, 파라미터 바인딩은 반드시 ? 플레이스홀더 사용
- pandas import하여 결과가 테이블이면 DataFrame으로 반환
- 함수에 docstring 포함
- SQL Injection 방지를 위해 동적 SQL의 정렬 컬럼 등은 화이트리스트 검증
- 완전한 실행 가능 코드만 출력 (설명 없이 코드 블록만)
"""


def build_few_shot_section(num_examples: int = 3) -> str:
    """퓨샷 예시 섹션을 만듭니다."""
    examples = ALL_EXAMPLES[:num_examples]
    parts: list[str] = []
    for i, ex in enumerate(examples, 1):
        parts.append(
            f"=== 예시 {i} ({ex['tag']}) ===\n"
            f"[SQL 입력]:\n{ex['sql']}\n\n"
            f"[Python 출력]:\n{ex['python']}"
        )
    return "\n\n".join(parts)


# ─────────── Gemma 프롬프트 ───────────
def build_gemma_prompt(sql_input: str, num_examples: int = 3) -> str:
    """Gemma 모델용 퓨샷 프롬프트를 생성합니다."""
    few_shot = build_few_shot_section(num_examples)
    return (
        f"<start_of_turn>user\n"
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"{few_shot}\n\n"
        f"=== 이제 아래 프로시저를 같은 방식으로 변환하세요 ===\n"
        f"[SQL 입력]:\n{sql_input}\n\n"
        f"[Python 출력]:\n"
        f"<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


# ─────────── GPT 프롬프트 (messages 형식) ───────────
def build_gpt_messages(
    sql_input: str,
    num_examples: int = 3,
    use_few_shot: bool = True,
) -> list[dict]:
    """OpenAI Chat Completion 형식의 messages를 생성합니다."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
    ]

    if use_few_shot:
        examples = ALL_EXAMPLES[:num_examples]
        for ex in examples:
            messages.append({
                "role": "user",
                "content": f"[SQL 입력]:\n{ex['sql']}\n\n[Python 출력]:",
            })
            messages.append({
                "role": "assistant",
                "content": ex["python"],
            })

    messages.append({
        "role": "user",
        "content": (
            f"[SQL 입력]:\n{sql_input}\n\n"
            f"[Python 출력]:"
        ),
    })
    return messages

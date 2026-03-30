"""
퓨샷 프롬프트 템플릿 빌더
Gemma / GPT 각각에 맞는 프롬프트를 생성합니다.

few_shot_examples.ALL_EXAMPLES 의 앞쪽 num_examples 개만 사용 (1~10).
"""
from __future__ import annotations

from .few_shot_examples import ALL_EXAMPLES

# ─────────── 시스템 지침 (공통) ───────────
SYSTEM_INSTRUCTION = """\
당신은 MS SQL Server 저장 프로시저를 Python 코드로 변환하는 전문가입니다.

=== 변환 규칙 ===

[구조 변환]
1. DECLARE 변수       → Python 함수 파라미터 (타입힌트 포함)
2. SELECT INTO #temp  → pandas DataFrame
3. CURSOR / WHILE     → pandas 벡터 연산 또는 리스트 컴프리헨션
4. TRY...CATCH        → try...except (ValueError 와 Exception 구분)
5. EXEC / sp_executesql → cursor.execute() (? 플레이스홀더 필수)
6. OUTPUT 파라미터     → dataclass return 값
7. BEGIN TRAN / COMMIT → conn.autocommit = False + conn.commit() / conn.rollback()
8. MERGE              → SELECT 존재 여부 확인 후 INSERT or UPDATE
9. SET NOCOUNT ON     → 생략
10. @@ROWCOUNT        → cursor.rowcount

[T-SQL 함수 변환]
11. GETDATE()         → datetime.now()
12. ISNULL(a, b)      → a if a is not None else b
13. COALESCE(a, b)    → a or b
14. LEN()             → len()
15. SUBSTRING(s,i,n)  → s[i-1:i-1+n]
16. UPPER() / LOWER() → .upper() / .lower()
17. PIVOT / UNPIVOT   → pd.pivot_table() (SQL PIVOT 문법 사용 금지)

[금지 사항]
18. query.format()으로 SQL 직접 조립 금지
    → f-string + 화이트리스트 검증 후 문자열 연결 사용
19. cursor.execute("BEGIN TRANSACTION") 금지
    → conn.autocommit = False 사용
20. SCOPE_IDENTITY() 직접 조회 금지
    → cursor.lastrowid 사용

=== 반환 타입 기준 ===
- SELECT 결과 (여러 행)  → pd.DataFrame
- 단일 값 반환           → int / str / float 등 기본 타입
- 성공/실패 + 부가 정보  → @dataclass
- 반환 없는 DML          → None

=== 추가 요구사항 ===
- pyodbc 사용, 파라미터 바인딩은 반드시 ? 플레이스홀더 사용
- 함수에 docstring 포함 (한 줄 요약)
- SQL Injection 방지: 동적 정렬/컬럼은 화이트리스트 검증 필수
- 실제로 사용하는 import만 포함 (미사용 import 금지)
- 완전한 실행 가능 코드만 출력 (설명 없이 코드만)
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

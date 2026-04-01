"""
퓨샷 프롬프트 템플릿 빌더
Gemma / Ollama 각각에 맞는 프롬프트를 생성합니다.

few_shot_examples.ALL_EXAMPLES(YAML 로드)의 앞쪽 num_examples 개만 사용.
"""
from __future__ import annotations

from .few_shot_examples import ALL_EXAMPLES

# ─────────── 시스템 지침 (공통) ───────────
SYSTEM_INSTRUCTION = """\
당신은 MS SQL Server 저장 프로시저를 Python 코드로 변환하는 전문가입니다.

=== [출력 — 위반 시 잘못된 응답] ===
- 자연어 설명·단계 요약·머리말/맺음말·대안 제안 일절 금지.
- 응답은 오직 실행 가능한 Python 소스만. (위 예시와 같이 import/def/class 로 구성)
- 마크다운이 필요하면 ```python ... ``` 단일 코드 펜스만 허용. 코드 밖 설명 문단 금지.
- SQLite / PostgreSQL 전용 문법·함수·드라이버·예시 금지.
  (예: sqlite3, psycopg2, asyncpg, PRAGMA, SERIAL, RETURNING 절, SQLite 파일 경로 등)
- 대상 DB는 항상 Microsoft SQL Server. SQL 문자열은 입력 프로시저와 동일한 T-SQL 의미를 유지.
- 프로시저의 분기·루프·트랜잭션·에러 처리·파라미터 의미를 임의로 단순화하거나 바꾸지 말 것.

=== 변환 규칙 ===

[구조 변환]
1. DECLARE 변수       → Python 함수 파라미터 (타입힌트 포함)
2. SELECT INTO #temp  → pandas DataFrame
3. CURSOR / WHILE     → pandas 벡터 연산 또는 리스트 컴프리헨션
4. TRY...CATCH        → try...except (ValueError 와 Exception 구분)
5. EXEC / sp_executesql → cursor.execute() (? 플레이스홀더 필수)
6. OUTPUT 파라미터     → dataclass return 값
7. 트랜잭션(pyodbc)
   - 연 직후 `conn.autocommit = False` 설정.
   - 원본에 BEGIN TRAN/COMMIT/ROLLBACK이 있으면 그 흐름에 맞춰 `conn.commit()` /
     `conn.rollback()` 배치.
   - 원본에 명시 트랜잭션이 없어도 INSERT/UPDATE/DELETE/MERGE 등 **쓰기 DML**이 있으면
     반드시 성공 경로에서 `conn.commit()`, `except` 블록에서 `conn.rollback()` 호출
     (pyodbc 기본은 autocommit=False라 생략 시 변경이 DB에 반영되지 않을 수 있음).
   - SELECT 등 읽기만 수행하면 commit/rollback 생략 가능.
8. MERGE              → SELECT 존재 여부 확인 후 INSERT or UPDATE
9. SET NOCOUNT ON     → 생략
10. @@ROWCOUNT        → cursor.rowcount

[T-SQL 함수 변환]
11. GETDATE()         → datetime.now() — SQL 문자열에 GETDATE() 남기지 말 것.
                        ? 플레이스홀더로 전달하고 Python에서 datetime.now() 사용.
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
21. cursor.messages, cursor.rownumber 사용 금지
    → pyodbc에 존재하지 않는 속성. cursor.rowcount 사용.

=== 반환 타입 기준 (반드시 준수) ===
- SELECT 결과 (여러 행)          → pd.DataFrame
- 단일 집계값                    → int / float 등 기본 타입
- 쓰기 DML (INSERT/UPDATE/DELETE) → @dataclass (success: bool, error_message: str | None)
- UPSERT                         → @dataclass (action: str, success: bool, error_message: str | None)
- 대량 삽입 (bulk)               → @dataclass (inserted_count: int, success: bool, error_message: str | None)
- 반환 없는 DML                  → None

=== 추가 요구사항 ===
- DB 접근은 **pyodbc** 만 사용. 파라미터 바인딩은 반드시 ? 플레이스홀더.
- 쓰기 DML이 하나라도 있으면 `commit`/`rollback` 누락 금지 (위 규칙 7).
- 함수에 docstring 한 줄만 (자연어 설명문·주석으로 동작을 장황히 풀지 말 것)
- SQL Injection 방지: 동적 정렬/컬럼은 화이트리스트 검증 필수
- 실제로 사용하는 import만 포함 (미사용 import 금지)
- 기본값 없는 파라미터는 기본값 있는 파라미터보다 반드시 앞에 위치
  (Python 문법: non-default argument follows default argument 방지)

=== 필수 출력 패턴 ===

[쓰기 DML — INSERT/UPDATE/DELETE/MERGE 등]
with pyodbc.connect(conn_str) as conn:
    conn.autocommit = False
    with closing(conn.cursor()) as cursor:
        try:
            cursor.execute(...)
            conn.commit()
            return XxxResult(success=True)
        except Exception as e:
            conn.rollback()
            return XxxResult(success=False, error_message=str(e))

[읽기 전용 — SELECT만]
with pyodbc.connect(conn_str) as conn:
    df = pd.read_sql(query, conn, params=[...])
return df

[커서]
- `from contextlib import closing` 임포트 후
  `with closing(conn.cursor()) as cursor:` 로 감쌀 것.
- pd.read_sql만 사용하는 읽기 전용 함수는 생략 가능.

[에러 메시지]
- `str(e)` 또는 `f"{type(e).__name__}: {e}"` 사용.
- `f"Line {e.__class__.__name__}: ..."` 형식 금지.
  (T-SQL ERROR_LINE()은 소스 줄 번호이며 Python 예외 클래스명이 아님)
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


# ─────────── Gemma/Ollama 공통 프롬프트 ───────────
def build_gemma_prompt(sql_input: str, num_examples: int = 3) -> str:
    """Gemma / Ollama 모델용 퓨샷 프롬프트를 생성합니다."""
    few_shot = build_few_shot_section(num_examples)
    return (
        f"<start_of_turn>user\n"
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"{few_shot}\n\n"
        f"=== 이제 아래 T-SQL 프로시저만 변환하세요 (위 규칙·예시와 동일한 출력 형식) ===\n"
        f"로직 보존 필수. 설명·SQLite/PostgreSQL·다른 DB 예시 금지. Python 코드만.\n"
        f"기본값 없는 파라미터는 기본값 있는 파라미터보다 반드시 앞에 위치할 것.\n"
        f"GETDATE()는 SQL에 남기지 말고 datetime.now()로 변환할 것.\n\n"
        f"[SQL 입력]:\n{sql_input}\n\n"
        f"[Python 출력]:\n"
        f"<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


# ─────────── GPT 프롬프트 (messages 형식, 비활성화) ───────────
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
            "T-SQL 로직 그대로 보존. 설명 금지. SQLite/PostgreSQL 금지. Python 코드만.\n"
            "기본값 없는 파라미터는 기본값 있는 파라미터보다 반드시 앞에 위치할 것.\n"
            "GETDATE()는 SQL에 남기지 말고 datetime.now()로 변환할 것.\n\n"
            f"[SQL 입력]:\n{sql_input}\n\n"
            f"[Python 출력]:"
        ),
    })
    return messages

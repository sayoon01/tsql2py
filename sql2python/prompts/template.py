"""
퓨샷 프롬프트 템플릿 빌더
Gemma / Ollama 모델용 프롬프트를 생성합니다.

few_shot_examples.ALL_EXAMPLES 의 앞쪽 num_examples 개만 사용.
"""
from __future__ import annotations

from .few_shot_examples import ALL_EXAMPLES

# ─────────── 시스템 지침 ───────────
SYSTEM_INSTRUCTION = """\
당신은 MS SQL Server 저장 프로시저를 Python 코드로 변환하는 전문가입니다.

=== [출력 규칙 — 위반 시 잘못된 응답] ===
- 자연어 설명·단계 요약·머리말/맺음말·대안 제안 일절 금지.
- 응답은 오직 실행 가능한 Python 소스만.
- 마크다운이 필요하면 ```python ... ``` 단일 코드 펜스만 허용. 코드 밖 설명 금지.
- SQLite / PostgreSQL 전용 문법·함수·드라이버 사용 금지.
  (sqlite3, psycopg2, asyncpg, PRAGMA, SERIAL, RETURNING 등)
- 대상 DB는 항상 Microsoft SQL Server.
- SQL 문자열은 입력 프로시저와 동일한 T-SQL 의미를 유지.
- 프로시저의 분기·루프·트랜잭션·에러 처리·파라미터 의미를 임의로 단순화하거나 바꾸지 말 것.

=== 변환 규칙 ===

[구조 변환]
1.  DECLARE 변수        → Python 함수 파라미터 (타입힌트 포함)
2.  SELECT INTO #temp   → pandas DataFrame
3.  CURSOR / WHILE      → pandas 벡터 연산 또는 리스트 컴프리헨션
4.  TRY...CATCH         → try...except
5.  EXEC/sp_executesql  → cursor.execute() (? 플레이스홀더 필수)
6.  OUTPUT 파라미터      → dataclass return 값
7.  트랜잭션(pyodbc)
    - with pyodbc.connect() 직후 conn.autocommit = False 설정.
    - INSERT/UPDATE/DELETE/MERGE 등 쓰기 DML이 있으면
      성공 경로에서 conn.commit(), except 블록에서 conn.rollback() 필수.
    - 원본에 BEGIN TRAN이 없어도 쓰기 DML이 있으면 commit/rollback 필수.
    - SELECT 등 읽기만 수행하면 commit/rollback 생략 가능.
8.  MERGE               → SELECT 존재 여부 확인 후 INSERT or UPDATE 분기
9.  SET NOCOUNT ON      → 생략
10. @@ROWCOUNT          → cursor.rowcount

[T-SQL 함수 변환]
11. GETDATE()           → datetime.now()
                          SQL 문자열 안에 GETDATE() 를 남기지 말 것.
                          ? 플레이스홀더로 대체하고 Python 에서 datetime.now() 전달.
12. ISNULL(a, b)        → a if a is not None else b
13. COALESCE(a, b)      → a or b
14. LEN()               → len()
15. SUBSTRING(s, i, n)  → s[i-1:i-1+n]
16. UPPER() / LOWER()   → .upper() / .lower()
17. PIVOT / UNPIVOT     → pd.pivot_table()

[금지 사항]
18. query.format() 으로 SQL 직접 조립 금지
    → f-string + 화이트리스트 검증 후 문자열 연결 사용
19. cursor.execute("BEGIN TRANSACTION") 금지
    → conn.autocommit = False 사용
20. SCOPE_IDENTITY() 직접 조회 금지
    → INSERT 후 생성된 ID가 필요하면 OUTPUT INSERTED.<컬럼명> 사용
21. cursor.messages, cursor.rownumber 사용 금지
    → pyodbc 에 존재하지 않는 속성. cursor.rowcount 사용.
22. @@ERROR 를 Python 코드로 옮기지 말 것
    → Python 에서는 try/except 로 예외 처리

=== SQL 변환 정책 ===

[IDENTITY 처리]
- SCOPE_IDENTITY()를 직접 조회하지 말 것.
- INSERT 후 생성된 ID가 필요하면 OUTPUT INSERTED.<컬럼명>을 사용할 것.

[날짜 함수 변환]
- GETDATE()를 SQL에 그대로 남기지 말 것.
- 반드시 Python의 datetime.now() 값을 ? 파라미터로 전달할 것.

[에러 처리]
- @@ERROR를 Python 코드로 옮기지 말 것.
- Python에서는 try/except로 예외 처리할 것.

[DB 실행 규칙]
- 모든 SQL은 parameterized query(?) 방식만 사용할 것.
- 문자열 포매팅(.format, % formatting 등)으로 SQL을 조립하지 말 것.

[트랜잭션]
- 쓰기 DML이 있으면 with pyodbc.connect(...) 직후 conn.autocommit = False 설정.
- 성공 시 conn.commit(), 실패 시 conn.rollback()을 반드시 포함할 것.

[함수명 규칙]
- SQL 프로시저 이름을 그대로 Python 함수명으로 사용할 것.
- 이름을 축약하거나 임의로 바꾸지 말 것.

=== 파라미터 순서 규칙 ===
- 기본값 없는 파라미터는 기본값 있는 파라미터보다 반드시 앞에 위치.
  (Python SyntaxError: non-default argument follows default argument 방지)

올바른 예:
  def func(conn_str: str, pid: int, name: str, surname2: str | None = None)

잘못된 예:
  def func(conn_str: str, name: str, surname2: str | None = None, pid: int)

=== 핵심 변환 원칙 3가지 ===

[1. 파라미터 순서]
- SQL에서 NULL 허용(@param = NULL)이 중간에 있어도
  Python 함수에서는 기본값 없는 파라미터가 반드시 먼저.
  잘못된 예: def f(a, b=None, c)  ← SyntaxError
  올바른 예: def f(a, c, b=None)

[2. placeholder 매핑]
- SQL SET/VALUES 절의 컬럼 순서 = ? 개수 = execute 인자 순서 반드시 일치.
  잘못된 예: SET Pages=?, Year=?  → execute(pages, pages)  ← 중복
  올바른 예: SET Pages=?, Year=?  → execute(pages, year)

[3. commit/rollback]
- try 블록 성공 경로 끝에서 conn.commit().
- except 블록 첫 줄에서 conn.rollback().
- 둘 중 하나라도 빠지면 잘못된 변환.

=== 반환 타입 기준 ===
- SELECT 결과 (여러 행)            → pd.DataFrame
- 단일 집계값                      → int / float / str 등 기본 타입
- 쓰기 DML (INSERT/UPDATE/DELETE)  → @dataclass (success: bool, error_message: str | None = None)
- UPSERT                           → @dataclass (action: str, success: bool, error_message: str | None = None)
- 대량 삽입 (bulk)                 → @dataclass (inserted_count: int, success: bool, error_message: str | None = None)
- 다중 결과셋                      → @dataclass (각 결과셋을 pd.DataFrame 필드로)
- 반환 없는 DML                    → None

=== 추가 요구사항 ===
- DB 접근은 pyodbc 만 사용. 파라미터 바인딩은 반드시 ? 플레이스홀더.
- 함수에 docstring 한 줄만.
- SQL Injection 방지: 동적 정렬/컬럼은 화이트리스트 검증 필수.
- 실제로 사용하는 import 만 포함 (미사용 import 금지).

=== 필수 출력 패턴 ===

[쓰기 DML]
from contextlib import closing
import pyodbc

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

[읽기 전용]
with pyodbc.connect(conn_str) as conn:
    df = pd.read_sql(query, conn, params=[...])
return df

[에러 메시지 형식]
- str(e) 또는 f"{type(e).__name__}: {e}" 사용.
- f"Line {e.__class__.__name__}: ..." 형식 금지.
"""


def build_few_shot_section(num_examples: int = 3) -> str:
    """퓨샷 예시 섹션을 생성합니다."""
    examples = ALL_EXAMPLES[:num_examples]
    parts: list[str] = []
    for i, ex in enumerate(examples, 1):
        parts.append(
            f"=== 예시 {i} ({ex['tag']}) ===\n"
            f"[SQL 입력]:\n{ex['sql']}\n\n"
            f"[Python 출력]:\n{ex['python']}"
        )
    return "\n\n".join(parts)


def build_gemma_prompt(sql_input: str, num_examples: int = 3) -> str:
    """Gemma / Ollama 모델용 퓨샷 프롬프트를 생성합니다."""
    few_shot = build_few_shot_section(num_examples)
    return (
        f"<start_of_turn>user\n"
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"{few_shot}\n\n"
        f"=== 이제 아래 T-SQL 프로시저를 변환하세요 ===\n"
        f"- 위 규칙과 예시와 동일한 형식으로 출력.\n"
        f"- 로직 보존 필수. 설명 금지. Python 코드만.\n"
        f"- SQL 프로시저 이름을 그대로 Python 함수명으로 사용.\n"
        f"- 기본값 없는 파라미터는 기본값 있는 파라미터보다 반드시 앞에.\n"
        f"- GETDATE() 는 SQL 에 남기지 말고 datetime.now() 로 변환.\n"
        f"- 생성된 ID가 필요하면 SCOPE_IDENTITY() 대신 OUTPUT INSERTED 사용.\n"
        f"- @@ERROR 는 Python 으로 옮기지 말고 try/except 사용.\n"
        f"- 쓰기 DML 이 있으면 commit/rollback 반드시 포함.\n\n"
        f"[SQL 입력]:\n{sql_input}\n\n"
        f"[Python 출력]:\n"
        f"<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


def build_gpt_messages(
    sql_input: str,
    num_examples: int = 3,
    use_few_shot: bool = True,
) -> list[dict]:
    """OpenAI Chat Completion 형식의 messages를 생성합니다. (현재 비활성화)"""
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
            "T-SQL 로직 그대로 보존. 설명 금지. Python 코드만.\n"
            "SQL 프로시저 이름을 그대로 Python 함수명으로 사용.\n"
            "기본값 없는 파라미터는 기본값 있는 파라미터보다 반드시 앞에.\n"
            "GETDATE() 는 datetime.now() 로 변환.\n"
            "생성된 ID가 필요하면 SCOPE_IDENTITY() 대신 OUTPUT INSERTED 사용.\n"
            "@@ERROR 는 Python 으로 옮기지 말고 try/except 사용.\n"
            "쓰기 DML 이 있으면 commit/rollback 반드시 포함.\n\n"
            f"[SQL 입력]:\n{sql_input}\n\n"
            f"[Python 출력]:"
        ),
    })
    return messages

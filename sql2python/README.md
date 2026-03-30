# SQL2Python

MS SQL Server 저장 프로시저를 Python 코드로 자동 변환하는 도구입니다.
**Gemma 3 12B / Qwen2.5-Coder 14B / GLM-4.5-Air 12B** 3개 모델을 퓨샷 프롬프팅으로 비교합니다.

---

## 설치
```bash
pip install -r requirements.txt
```

### 필수 환경

- Python 3.10+
- CUDA GPU (로컬 모델 실행 시)
  - 12B 모델: 16GB+ VRAM (4bit 양자화 시 8GB+)
  - 14B 모델: 16GB+ VRAM (4bit 양자화 시 10GB+)
- HuggingFace 토큰 (Gemma 접근용)
```bash
export HF_TOKEN="hf_..."   # HuggingFace 토큰
```

> GPT는 현재 비활성화 상태입니다.
> 사용하려면 `config.yaml`의 `gpt:` 블록 주석을 해제하고
> `OPENAI_API_KEY` 환경변수를 설정하세요.

---

## 사용법
```bash
# 단일 파일 변환 (모델 선택: gemma / qwen / glm)
python main.py convert --backend gemma --input examples/sql/usp_modified_book_storebook.sql
python main.py convert --backend qwen  --input examples/sql/usp_modified_book_storebook.sql
python main.py convert --backend glm   --input examples/sql/usp_modified_book_storebook.sql

# 퓨샷 예시 수 지정 (기본 3개, 최대 10개)
python main.py convert --backend gemma \
  --input examples/sql/usp_modified_book_storebook.sql \
  --num-examples 10

# 3개 모델 동시 비교 (기본 퓨샷 3개)
python main.py compare --input examples/sql/usp_add_authorbook_storebook.sql

# 퓨샷 10개로 3개 모델 비교
python main.py compare \
  --input examples/sql/usp_add_authorbook_storebook.sql \
  --num-examples 10

# 전체 SQL 일괄 변환 + 비교 (배치)
python main.py batch --input-dir examples/sql/ --output-dir output/

# 배치 + 퓨샷 10개
python main.py batch \
  --input-dir examples/sql/ \
  --num-examples 10 \
  --output-dir output/

# 프롬프트 미리보기 (모델 호출 없이)
python main.py preview \
  --input examples/sql/usp_modified_book_storebook.sql \
  --backend gemma \
  --num-examples 10
```

---

## 추천 워크플로우

실제 대량 변환 전에 **단일 파일 비교로 품질을 먼저 확인**한 뒤 `batch`로 확장하는 걸 권장합니다.

### 1) 단일 파일 빠른 테스트 (퓨샷 3개)
```bash
python main.py compare \
  --input examples/sql/usp_add_authorbook_storebook.sql \
  --num-examples 3 \
  --output-dir output/
```

### 2) 단일 파일 정밀 비교 (퓨샷 10개 전체)
```bash
python main.py compare \
  --input examples/sql/usp_add_authorbook_storebook.sql \
  --num-examples 10 \
  --output-dir output/
```

### 3) 배치 처리 (퓨샷 10개)
```bash
python main.py batch \
  --input-dir examples/sql/ \
  --num-examples 10 \
  --output-dir output/
```

> **퓨샷 예시 수 선택 가이드**
> ```
> --num-examples 3   → 빠른 테스트, 토큰 절약
> --num-examples 5   → 균형 (추천)
> --num-examples 10  → 최고 품질, 토큰 2배 소모
> ```

---

## 프로젝트 구조
```
sql2python/
├── main.py                   # CLI 진입점
├── config.yaml               # 모델/생성 파라미터 설정
├── requirements.txt
├── prompts/
│   ├── few_shot_examples.py  # 퓨샷 예시 10종 (ALL_EXAMPLES)
│   ├── template.py           # 프롬프트 빌더 (Gemma/Qwen/GLM 공통)
│   └── post_process.py       # 생성 코드 후처리 (누락 import 보완)
├── converters/
│   ├── gemma_converter.py    # HuggingFace Gemma 3 12B 변환기
│   ├── qwen_converter.py     # HuggingFace Qwen2.5-Coder 14B 변환기
│   ├── glm_converter.py      # HuggingFace GLM-4.5-Air 12B 변환기
│   ├── gpt_converter.py      # OpenAI GPT 변환기 (현재 비활성화)
│   └── comparator.py         # 품질 분석 및 3-way 비교 엔진
├── examples/sql/             # BookStore 샘플 프로시저 (usp_*.sql 4개)
└── output/                   # 변환 결과 저장
```

### 각 모듈의 역할

| 파일/모듈 | 역할 |
|---|---|
| **main.py** | CLI 진입점. `convert` / `compare` / `batch` / `preview` 4가지 커맨드 |
| **config.yaml** | 모델명, temperature, max_new_tokens 등 설정 |
| **prompts/template.py** | SQL → 프롬프트 변환. Gemma/Qwen/GLM 공통 프롬프트 템플릿 |
| **prompts/few_shot_examples.py** | 10종 SQL→Python 퓨샷 쌍. `--num-examples 1~10`으로 선택 |
| **prompts/post_process.py** | 생성 코드 보정 (누락 `date` import 등 자동 보완) |
| **converters/gemma_converter.py** | Gemma 3 12B 로컬 추론. `device_map=cuda:0`, OOM 처리 포함 |
| **converters/qwen_converter.py** | Qwen2.5-Coder 14B 로컬 추론. chat template 방식 |
| **converters/glm_converter.py** | GLM-4.5-Air 12B 로컬 추론. apply_chat_template + tokenize=True |
| **converters/gpt_converter.py** | OpenAI GPT 변환기 (비활성화, 주석처리 상태) |
| **converters/comparator.py** | 3개 모델 결과 비교 및 품질 점수 계산 (0~100점) |

---

### 실행 흐름

#### 1️⃣ 단일 변환 (convert)
```
main.py (CLI 입력)
  ↓
config.yaml (설정 로드)
  ↓
[모델 선택: gemma / qwen / glm]
  ↓
prompts/template.py
  → few_shot_examples.py에서 num_examples개 예시 선택
  → 프롬프트 빌드
  ↓
converters/[모델]_converter.py
  → 모델 로드 (4bit 양자화)
  → 추론 실행
  → 코드 추출
  → post_process.py (import 보완)
  ↓
output/ 에 Python 파일 저장
```

#### 2️⃣ 3-way 비교 (compare)
```
main.py (compare 커맨드)
  ↓
Gemma 변환 → unload_model()
  ↓
Qwen 변환  → unload_model()
  ↓
GLM 변환   → unload_model()
  ↓
converters/comparator.py
  ├─ AST 구문 검증
  ├─ 타입힌트 / docstring / 파라미터 바인딩 등 확인
  └─ 품질 점수 계산 (0~100)
  ↓
3-way 비교 테이블 출력 + JSON 리포트 저장
```

#### 3️⃣ 배치 처리 (batch)
```
main.py (batch 커맨드)
  ↓
SQL 파일 목록 수집 (*.sql)
  ↓
파일마다 반복:
  Gemma 변환 → unload
  Qwen 변환  → unload
  GLM 변환   → unload
  3-way 비교 테이블 출력
  ↓
전체 요약 테이블 + batch_report.json 저장
```

---

## 퓨샷 예시 (`prompts/few_shot_examples.py`)

`ALL_EXAMPLES`에 **10종** SQL→Python 쌍이 있으며,
`--num-examples`(1~10)만큼 앞에서부터 프롬프트에 포함됩니다.

| 순서 | tag | 요약 |
|---|---|---|
| 1 | `simple_select` | 단순 SELECT + `?` 바인딩 |
| 2 | `transaction` | 트랜잭션 · OUTPUT · TRY/CATCH |
| 3 | `temp_table` | 임시 집계 테이블 · JOIN 일괄 UPDATE |
| 4 | `dynamic_sql` | 페이지 / 정렬 검증 · 동적 SQL |
| 5 | `merge_upsert` | UPDATE 후 ROWCOUNT 기반 INSERT |
| 6 | `soft_delete` | Soft delete · 삭제 로그 |
| 7 | `bulk_insert` | 스테이징 · 중복 제외 일괄 삽입 |
| 8 | `scalar_aggregate` | 집계 OUTPUT → dataclass |
| 9 | `multiple_resultset` | 여러 SELECT → nextset() · DataFrame |
| 10 | `cte_ranking` | CTE · ROW_NUMBER · Top-N |

---

## 모델별 특징 및 선택 가이드

| 모델 | 파라미터 | VRAM (4bit) | 속도 | 코드 품질 | 비용 |
|---|---|---|---|---|---|
| **Gemma 3 12B** | 12B | ~8GB | 중간 | 좋음 | 무료 |
| **Qwen2.5-Coder 14B** | 14B | ~10GB | 중간 | 매우 좋음 | 무료 |
| **GLM-4.5-Air 12B** | 12B | ~8GB | 빠름 | 좋음 | 무료 |
| ~~GPT-4o~~ | - | 불필요 | 매우 빠름 | 최고 | 유료 |

> **추천**: Qwen2.5-Coder는 코드 특화 모델이라 SQL→Python 변환에 유리합니다.

---

## 품질 점수 기준 (comparator.py)

| 항목 | 점수 |
|---|---|
| 구문 유효 (AST parse 통과) | +30점 |
| 파라미터 바인딩 (`?` 플레이스홀더) | +20점 |
| 타입힌트 포함 | +15점 |
| 에러 처리 (try/except) | +15점 |
| docstring 포함 | +10점 |
| Context Manager (with conn) | +10점 |
| **합계** | **100점** |

---

## 예제 입력 SQL (`examples/sql/`)

BookStore DB 스크립트:

| 파일명 | 내용 |
|---|---|
| `usp_modified_book_storebook.sql` | 도서 정보 수정 + OUTPUT |
| `usp_add_authorbook_storebook.sql` | 저자-도서 연결 INSERT + OUTPUT |
| `usp_modified_author_storebook.sql` | 저자 정보 수정 + OUTPUT |
| `usp_delete_book_storebook.sql` | 관련 행 삭제 + 트랜잭션 |

---

## 라이선스

MIT
```

---

## 주요 변경 사항
```
① 제목/설명  →  GPT → Gemma/Qwen/GLM 3개 모델로 변경
② 설치/환경  →  OpenAI 키 제거, HF_TOKEN만 필요
③ 사용법     →  --num-examples 옵션 예시 추가
               GPT 관련 명령어 제거
               --include-zero-shot 제거
④ 워크플로우 →  퓨샷 3/5/10개 선택 가이드 추가
⑤ 구조      →  qwen_converter, glm_converter 추가
               gpt_converter 비활성화 표시
⑥ 실행 흐름 →  3-way 비교 + unload_model() 흐름 추가
               배치 흐름 추가
⑦ 모델 비교 →  Gemma/Qwen/GLM 특징 표 추가
⑧ 품질 점수 →  채점 기준 표 추가
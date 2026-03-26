# tsql2py

MS SQL Server(T‑SQL) 저장 프로시저를 **실행 가능한 Python 코드**로 변환하는 실험용 도구입니다.  
로컬 Gemma(퓨샷 프롬프트)와 OpenAI GPT(API)를 같은 입력 조건에서 비교할 수 있습니다.

## 빠른 시작

- **문서/사용법**: `sql2python/README.md`
- **CLI 진입점**: `sql2python/main.py`

```bash
cd sql2python
pip install -r requirements.txt

# 프롬프트만 미리보기(모델 호출 없음)
python main.py preview --backend gemma --input examples/sql/sample1_simple_select.sql

# 공정 비교(기본): Gemma(퓨샷) vs GPT(퓨샷)
python main.py compare --input examples/sql/sample2_transaction_audit.sql
```
# tsql2py

MS SQL Server(T‑SQL) 저장 프로시저를 **실행 가능한 Python**으로 바꾸는 실험용 도구입니다.  
로컬 **[Ollama](https://ollama.com/)** 로 `sql2python/config.yaml` 의 세 `model_name` 을 같은 퓨샷 조건에서 **3-way 비교**합니다.

예제 T-SQL은 `sql2python/examples/sql/` 아래 BookStore용 `usp_*.sql` 등을 둡니다.

## 빠른 시작

- **상세 사용법·구조**: [`sql2python/README.md`](sql2python/README.md)
- **CLI**: `sql2python/main.py`

```bash
cd sql2python
pip install -r requirements.txt
# Ollama: ollama pull … 후 `ollama list` 이름이 config.yaml model_name 과 일치하는지 확인

python main.py compare \
  --input examples/sql/usp_add_authorbook_storebook.sql \
  --num-examples 11 \
  --plots   # 선택: output/report/ 에 품질·시간 비교 PNG 저장 (matplotlib 필요)
```

프롬프트·퓨샷·후처리·**Comparator(점수·JSON·차트)** 는 [`sql2python/README.md`](sql2python/README.md) 를 참고하세요.

import requests
import json
import sys

query = sys.argv[1] if len(sys.argv) > 1 else "查询各部门的员工数量"
r = requests.post("http://127.0.0.1:8000/api/query", json={"user_query": query}, timeout=120)
d = r.json()
print("STATUS:", d.get("status"))
print("SQL:", d.get("generated_sql", ""))
print("ROWS:", d.get("returned_rows", 0))
print("DURATION:", d.get("query_duration_ms", 0), "ms")
print("ANALYSIS:", d.get("analysis", ""))
print("ERROR:", d.get("error", ""))

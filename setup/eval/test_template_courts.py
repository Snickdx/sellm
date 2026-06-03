from pathlib import Path

from app.rag_backend import RequirementsRAG, SimpleLLM

rag = RequirementsRAG(str(Path(__file__).resolve().parents[2] / "data.xlsx"))
llm = SimpleLLM(rag)
for q in [
    "Who is involved in this project",
    "what do you mean by courts?",
    "what are courts",
]:
    print("Q:", q)
    print("A:", llm.generate_response(q))
    print()

from app.rag_backend import RequirementsRAG, SimpleLLM

# Scenario-first: no root data.xlsx. Queries without a persona hit the empty legacy collection.
rag = RequirementsRAG(excel_file=None)
llm = SimpleLLM(rag)
for q in [
    "Who is involved in this project",
    "what do you mean by courts?",
    "what are courts",
]:
    print("Q:", q)
    print("A:", llm.generate_response(q))
    print()

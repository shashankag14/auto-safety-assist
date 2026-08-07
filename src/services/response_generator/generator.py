from openai import OpenAI

from src.common.config import OPENAI_API_KEY, OPENAI_MODEL, RESPONSE_INSTRUCTIONS


def build_context(results: list[tuple]) -> str:
    lines = []
    for source, id, vehicle_tag, text, cosine_sim in results:
        lines.append(f"[{source} {id} | {vehicle_tag}]\n{text}")
    return "\n\n".join(lines)


def generate_response(query: str, candidates: list[tuple], model: str = OPENAI_MODEL) -> str:
    # build the context in string format
    context = build_context(candidates)

    client = OpenAI(api_key=OPENAI_API_KEY)
    input_text = f"Context:\n{context}\n\nQuestion: {query}"

    response = client.responses.create(
        model=model,
        instructions=RESPONSE_INSTRUCTIONS,
        input=input_text,
    )

    return response.output_text

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

_JUDGE_SYSTEM_PROMPT = """You are grading a RAG (retrieval-augmented generation) system's \
answer to a question. Score the answer on three dimensions, each on a 1-5 scale:

- faithfulness: Is the answer grounded in the retrieved context, with no fabricated claims?
  1 = fabricated or contradicts the context, 5 = fully supported by the context.
- relevance: Does the answer address the question that was actually asked?
  1 = off-topic or non-responsive, 5 = directly and completely addresses the question.
- correctness: Does the answer match the reference answer's factual content?
  1 = wrong or contradicts the reference, 5 = matches the reference answer's key facts.

Provide a short (1-2 sentence) reasoning justifying your scores."""

_JUDGE_USER_TEMPLATE = """Question:
{question}

Reference answer:
{reference_answer}

Retrieved context (what the system actually had access to):
{retrieved_context}

Generated answer to grade:
{generated_answer}"""


class JudgeScore(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    correctness: int = Field(ge=1, le=5)
    reasoning: str


_judge_llm = None


def _get_judge_llm(model: str):
    """Create and cache the structured-output judge LLM on first use."""
    global _judge_llm
    if _judge_llm is not None:
        return _judge_llm

    from langchain_openai import ChatOpenAI

    _judge_llm = ChatOpenAI(model=model, temperature=0).with_structured_output(JudgeScore)
    return _judge_llm


def judge_answer(
    question: str,
    reference_answer: str,
    generated_answer: str,
    retrieved_context: str,
    model: str = "gpt-4o-mini",
) -> Optional[Dict[str, Any]]:
    """
    Score a generated answer against a reference answer and the context the agent
    actually retrieved, using an LLM as judge.

    Returns a dict with faithfulness/relevance/correctness/reasoning, or None if
    the judge call fails for any reason (so a single bad grading call doesn't
    abort the whole eval run).
    """
    try:
        llm = _get_judge_llm(model)
        result: JudgeScore = llm.invoke(
            [
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _JUDGE_USER_TEMPLATE.format(
                        question=question,
                        reference_answer=reference_answer,
                        retrieved_context=retrieved_context or "No context was retrieved.",
                        generated_answer=generated_answer or "(empty answer)",
                    ),
                },
            ]
        )
        return result.model_dump()
    except Exception:
        return None

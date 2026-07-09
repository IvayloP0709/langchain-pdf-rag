import src.eval.judge as judge_module
from src.eval.judge import JudgeScore, judge_answer


class FakeJudgeLLM:
    def __init__(self, result=None, raise_error=False):
        self.result = result
        self.raise_error = raise_error
        self.last_messages = None

    def invoke(self, messages):
        self.last_messages = messages
        if self.raise_error:
            raise RuntimeError("judge call failed")
        return self.result


def test_judge_answer_returns_scores(monkeypatch):
    fake_result = JudgeScore(
        faithfulness=4, relevance=5, correctness=3, reasoning="Mostly grounded."
    )
    fake_llm = FakeJudgeLLM(result=fake_result)
    monkeypatch.setattr(judge_module, "_get_judge_llm", lambda model: fake_llm)

    result = judge_answer(
        question="What is RAG?",
        reference_answer="RAG combines retrieval with generation.",
        generated_answer="RAG retrieves documents then generates an answer.",
        retrieved_context="Document 1: RAG combines retrieval and generation.",
    )

    assert result == {
        "faithfulness": 4,
        "relevance": 5,
        "correctness": 3,
        "reasoning": "Mostly grounded.",
    }
    # question, reference, context, and generated answer should all reach the prompt
    user_content = fake_llm.last_messages[1]["content"]
    assert "What is RAG?" in user_content
    assert "RAG combines retrieval with generation." in user_content


def test_judge_answer_returns_none_on_exception(monkeypatch):
    fake_llm = FakeJudgeLLM(raise_error=True)
    monkeypatch.setattr(judge_module, "_get_judge_llm", lambda model: fake_llm)

    result = judge_answer(
        question="q",
        reference_answer="ref",
        generated_answer="gen",
        retrieved_context="ctx",
    )

    assert result is None


def test_judge_answer_handles_missing_context(monkeypatch):
    fake_result = JudgeScore(faithfulness=1, relevance=1, correctness=1, reasoning="No context.")
    fake_llm = FakeJudgeLLM(result=fake_result)
    monkeypatch.setattr(judge_module, "_get_judge_llm", lambda model: fake_llm)

    result = judge_answer(
        question="q",
        reference_answer="ref",
        generated_answer="",
        retrieved_context="",
    )

    assert result["faithfulness"] == 1
    user_content = fake_llm.last_messages[1]["content"]
    assert "No context was retrieved." in user_content
    assert "(empty answer)" in user_content

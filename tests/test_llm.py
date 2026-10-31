import json

import httpx
import pytest

from resurrect.llm import LLMConfig, LLMError, chat, check_ollama


def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_chat_non_streaming():
    seen = {}

    def handler(request):
        seen["payload"] = json.loads(request.content)
        seen["url"] = str(request.url)
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "hello"}, "done": True}
        )

    result = chat(
        "hi", system="be brief", config=LLMConfig(num_ctx=4096), client=make_client(handler)
    )
    assert result == "hello"
    assert seen["url"].endswith("/api/chat")
    assert seen["payload"]["options"]["num_ctx"] == 4096
    assert seen["payload"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert seen["payload"]["stream"] is False


def test_chat_streaming_collects_tokens():
    lines = [
        {"message": {"content": "Hel"}, "done": False},
        {"message": {"content": "lo"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    body = "\n".join(json.dumps(line) for line in lines).encode()
    tokens = []
    client = make_client(lambda request: httpx.Response(200, content=body))
    result = chat("hi", stream=True, on_token=tokens.append, client=client)
    assert result == "Hello"
    assert tokens == ["Hel", "lo"]


def test_model_not_found():
    client = make_client(lambda r: httpx.Response(404, json={"error": "model 'x' not found"}))
    with pytest.raises(LLMError, match="ollama pull"):
        chat("hi", config=LLMConfig(model="x"), client=client)


def test_ollama_not_running():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError, match="Cannot reach Ollama"):
        chat("hi", client=make_client(handler))


def test_check_ollama_ok_and_missing():
    def handler(request):
        return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:7b"}]})

    check_ollama(LLMConfig(), client=make_client(handler))
    with pytest.raises(LLMError, match="ollama pull"):
        check_ollama(LLMConfig(model="other:1b"), client=make_client(handler))
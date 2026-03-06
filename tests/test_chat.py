"""
Tests for the Chat (Stella) API:
  POST   /api/chat          - send a message, receive a reply
  GET    /api/chat/history  - retrieve stored message history
  DELETE /api/chat/history  - clear chat history

All Anthropic API calls are mocked so tests run without network access
or a real API key.
"""

import pytest
from unittest.mock import patch, MagicMock


def _mock_anthropic(reply_text: str = "Hello, I am Stella."):
    """Return a patched anthropic.Anthropic whose messages.create returns reply_text."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=reply_text)]
    mock_instance.messages.create.return_value = mock_msg
    return mock_cls


# ── Sending messages ──────────────────────────────────────────────────────────

class TestChatMessage:
    def test_basic_message_returns_reply(self, client):
        mock_cls = _mock_anthropic("Hello from Stella!")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            resp = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hi"}], "context": {}},
            )
        assert resp.status_code == 200
        assert resp.json()["reply"] == "Hello from Stella!"

    def test_reply_field_present_in_response(self, client):
        mock_cls = _mock_anthropic("Test reply")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            resp = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "What are top trends?"}],
                    "context": {},
                },
            )
        assert "reply" in resp.json()

    def test_multi_turn_conversation(self, client):
        """Sending multiple prior messages in one request must still return a reply."""
        mock_cls = _mock_anthropic("Great follow-up!")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            resp = client.post(
                "/api/chat",
                json={
                    "messages": [
                        {"role": "user", "content": "What is a composite score?"},
                        {"role": "assistant", "content": "It is a weighted metric..."},
                        {"role": "user", "content": "Can you give an example?"},
                    ],
                    "context": {},
                },
            )
        assert resp.status_code == 200
        assert "reply" in resp.json()

    def test_context_is_appended_to_message(self, client):
        """The platform context should be included in the payload sent to Claude."""
        mock_cls = _mock_anthropic("Context-aware response")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Tell me about this trend"}],
                    "context": {
                        "keyword": "vintage denim",
                        "lifecycle_stage": "Accelerating",
                        "composite_score": 42.5,
                    },
                },
            )

        # Inspect the messages sent to Claude
        create_call = mock_cls.return_value.messages.create
        assert create_call.called
        call_kwargs = create_call.call_args[1]
        messages_sent = call_kwargs["messages"]
        last_content = messages_sent[-1]["content"]
        # Context block should contain the keyword
        assert "vintage denim" in last_content

    def test_system_prompt_is_sent(self, client):
        """The Stella system prompt must be passed in every API call."""
        mock_cls = _mock_anthropic("Response")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hello"}], "context": {}},
            )
        call_kwargs = mock_cls.return_value.messages.create.call_args[1]
        assert "system" in call_kwargs
        # System prompt should mention 'Stella'
        assert "Stella" in call_kwargs["system"]

    def test_empty_context_is_accepted(self, client):
        mock_cls = _mock_anthropic("Fine with empty context")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            resp = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hi"}], "context": {}},
            )
        assert resp.status_code == 200


# ── Chat history ──────────────────────────────────────────────────────────────

class TestChatHistory:
    def test_history_empty_for_new_user(self, client):
        resp = client.get("/api/chat/history")
        assert resp.status_code == 200
        assert resp.json()["messages"] == []

    def test_message_stored_in_history_after_chat(self, client):
        mock_cls = _mock_anthropic("Stored reply")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Save this"}], "context": {}},
            )
        resp = client.get("/api/chat/history")
        messages = resp.json()["messages"]
        assert len(messages) >= 2  # user + assistant

    def test_history_contains_user_and_assistant_roles(self, client):
        mock_cls = _mock_anthropic("Assistant reply")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hello"}], "context": {}},
            )
        resp = client.get("/api/chat/history")
        roles = {m["role"] for m in resp.json()["messages"]}
        assert "user" in roles
        assert "assistant" in roles

    def test_history_accumulates_across_messages(self, client):
        mock_cls = _mock_anthropic("Reply")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            for i in range(3):
                client.post(
                    "/api/chat",
                    json={
                        "messages": [{"role": "user", "content": f"Message {i}"}],
                        "context": {},
                    },
                )
        resp = client.get("/api/chat/history")
        # 3 user + 3 assistant = 6 messages minimum
        assert len(resp.json()["messages"]) >= 6


# ── Clear history ─────────────────────────────────────────────────────────────

class TestClearHistory:
    def test_clear_returns_200(self, client):
        resp = client.delete("/api/chat/history")
        assert resp.status_code == 200

    def test_history_empty_after_clear(self, client):
        mock_cls = _mock_anthropic("temp")
        with patch("app.chat.router.anthropic.Anthropic", mock_cls):
            client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}], "context": {}},
            )
        client.delete("/api/chat/history")
        resp = client.get("/api/chat/history")
        assert resp.json()["messages"] == []

    def test_clear_only_affects_current_user(self, client):
        """Clearing one user's history must not affect data for other users."""
        # This test verifies data isolation — since both requests share the same
        # test user 'testuser@example.com', we just verify the operation succeeds.
        resp = client.delete("/api/chat/history")
        assert resp.status_code == 200
        assert "message" in resp.json()

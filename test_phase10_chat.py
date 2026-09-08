"""
Tests for AI Service Assistant Chatbot Endpoint (/chat)
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_chat_how_to_book_english():
    response = client.post("/chat", json={"message": "How do I book a plumbing service?", "language": "en"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "how_to_book"
    assert data["source"] == "knowledge_base"
    assert "book a service" in data["response"].lower()
    assert len(data["suggestions"]) > 0


def test_chat_how_to_book_tamil():
    response = client.post("/chat", json={"message": "நான் ஒரு சேவை முன்பதிவு செய்ய வேண்டும்", "language": "ta"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "how_to_book"
    assert "முன்பதிவு" in data["response"]


def test_chat_emergency_service():
    response = client.post("/chat", json={"message": "Emergency SOS pipe burst leaking"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "emergency_service"
    assert "Emergency" in data["response"]


def test_chat_payment_upi():
    response = client.post("/chat", json={"message": "What UPI payment options are supported?"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "payment_upi"
    assert "Razorpay" in data["response"] or "UPI" in data["response"]


def test_chat_ml_matching_explanation():
    response = client.post("/chat", json={"message": "Explain your AI matching algorithm and score"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "ml_matching"
    assert "45%" in data["response"]


def test_chat_welfare_benefits():
    response = client.post("/chat", json={"message": "What insurance and welfare schemes are available for workers?"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "welfare_benefits"
    assert "PMJJBY" in data["response"]


def test_chat_fallback():
    response = client.post("/chat", json={"message": "xyz random gibberish 12345"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "general_help"
    assert data["source"] == "default_assistant"
    assert len(data["suggestions"]) >= 3

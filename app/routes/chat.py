"""
Chat / Chatbot API routes — Cooperative Gig Services AI Assistant
Supports intent detection, FAQ matching, and multilingual responses (English + Tamil).
"""
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/chat", tags=["Service Assistant Chatbot"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User question or prompt")
    session_id: Optional[str] = Field(None, description="Optional session tracking ID")
    language: Optional[str] = Field("en", description="Preferred language code ('en' or 'ta')")


class ChatResponse(BaseModel):
    response: str
    source: str
    intent: str
    suggestions: List[str]
    session_id: Optional[str] = None


FAQ_KNOWLEDGE_BASE = [
    {
        "intent": "how_to_book",
        "keywords": ["book", "order", "schedule", "hire", "request service", "முன்பதிவு", "பதிவு", "ஆர்டர்"],
        "en": (
            "To book a service: 1) Select a service category (Plumbing, Electrical, Cleaning, etc.) "
            "or use the AI Problem Matcher, 2) Choose your preferred schedule, 3) Complete secure payment, "
            "and 4) Our hybrid dispatch engine automatically assigns the nearest verified cooperative worker."
        ),
        "ta": (
            "சேவை முன்பதிவு செய்ய: 1) சேவை வகையை (குழாய் பழுது, மின்சாரம், சுத்தம்) தேர்வு செய்யவும் அல்லது AI தேடலைப் பயன்படுத்தவும், "
            "2) நேரத்தைத் தேர்ந்தெடுக்கவும், 3) கட்டணம் செலுத்தவும், 4) அருகிலுள்ள சரிபார்க்கப்பட்ட கூட்டுறவு தொழிலாளர் தானாக நியமிக்கப்படுவார்."
        ),
        "suggestions": [
            "Emergency service",
            "Payment & UPI options",
            "How ML matching works?",
        ],
    },
    {
        "intent": "emergency_service",
        "keywords": ["emergency", "urgent", "sos", "danger", "burst", "hazard", "அவசரம்", "உடனடி", "ஆபத்து"],
        "en": (
            "Emergency SOS Service provides high-priority dispatch within minutes. "
            "Tap the red Emergency button on the home screen to alert on-call certified workers "
            "with zero delay."
        ),
        "ta": (
            "அவசர சேவை சில நிமிடங்களில் முன்னுரிமை ஒதுக்கீடு வழங்குகிறது. "
            "முகப்புத் திரையிலுள்ள சிவப்பு அவசர பொத்தானை அழுத்தவும்."
        ),
        "suggestions": [
            "How to book a service?",
            "Payment & UPI options",
            "Cooperative welfare benefits",
        ],
    },
    {
        "intent": "payment_upi",
        "keywords": ["payment", "pay", "upi", "razorpay", "gpay", "phonepe", "escrow", "கட்டணம்", "பணம்", "யூபிஐ"],
        "en": (
            "Payments are securely processed via Razorpay with full support for UPI (Google Pay, PhonePe, Paytm, Navi), "
            "Net Banking, and Cards. Funds are held in cooperative escrow and released only after verified OTP service completion."
        ),
        "ta": (
            "கட்டணங்கள் ரேஸர்பே மூலம் UPI (Google Pay, PhonePe), கார்டுகள் வழியாக பாதுகாப்பாக செலுத்தப்படுகின்றன. "
            "வேலை முடிந்து OTP சரிபார்க்கப்பட்ட பிறகே தொகை தொழிலாளருக்கு விடுவிக்கப்படும்."
        ),
        "suggestions": [
            "How ML matching works?",
            "Worker verification & KYC",
            "How to book a service?",
        ],
    },
    {
        "intent": "ml_matching",
        "keywords": ["ml", "ai", "matching", "algorithm", "score", "ranking", "பொருத்தம்", "அல்காரிதம்", "தரவரிசை"],
        "en": (
            "Our Hybrid AI Dispatch Engine uses Stage 1 hard eligibility filters (trade certifications, cooperative membership, "
            "radius), combined with 45% Rule Score + 35% ML Suitability (88% Top-1 Accuracy) + 20% Fairness Bonus, ensuring optimal and equitable worker allocation."
        ),
        "ta": (
            "எங்கள் ஹைப்ரிட் AI ஒதுக்கீட்டு முறை 45% விதிமுறை + 35% ML பொருத்தம் + 20% கூட்டுறவு சமபங்கு போனஸ் அடிப்படையில் செயல்படுகிறது."
        ),
        "suggestions": [
            "Worker verification & KYC",
            "Cooperative welfare benefits",
            "How to book a service?",
        ],
    },
    {
        "intent": "worker_kyc",
        "keywords": ["kyc", "verification", "verified", "aadhaar", "police", "safe", "சரிபார்ப்பு", "பாதுகாப்பு", "ஆதார்"],
        "en": (
            "Every cooperative worker undergoes multi-tier verification: Aadhaar eKYC, mobile OTP validation, "
            "skill trade certification check, and cooperative association vetting before receiving any jobs."
        ),
        "ta": (
            "ஒவ்வொரு தொழிலாளரும் ஆதார் eKYC, மொபைல் OTP, தொழில் சான்றிதழ் மற்றும் கூட்டுறவு சங்கத்தின் நேரடி சரிபார்ப்புக்குப் பின்னரே அனுமதிக்கப்படுகிறார்கள்."
        ),
        "suggestions": [
            "Cooperative welfare benefits",
            "How to book a service?",
            "Emergency service",
        ],
    },
    {
        "intent": "welfare_benefits",
        "keywords": ["welfare", "scheme", "insurance", "pension", "pmjjby", "pmsby", "நலத்திட்டம்", "காப்பீடு", "சலுகைகள்"],
        "en": (
            "Cooperative members are covered by government social security schemes including PMJJBY (₹2L Life Insurance), "
            "PMSBY (₹2L Accident Cover), Ayushman Bharat PM-JAY (₹5L Health Cover), plus our Cooperative Emergency Relief Fund."
        ),
        "ta": (
            "கூட்டுறவு உறுப்பினர்களுக்கு PMJJBY (₹2L ஆயுள் காப்பீடு), PMSBY (₹2L விபத்து காப்பீடு), மற்றும் கூட்டுறவு அவசர நிவாரண நிதி பலன்கள் கிடைக்கின்றன."
        ),
        "suggestions": [
            "How to book a service?",
            "Worker verification & KYC",
            "Payment & UPI options",
        ],
    },
    {
        "intent": "cancel_refund",
        "keywords": ["cancel", "refund", "reschedule", "ரத்து", "திருப்பி"],
        "en": (
            "You can cancel a booking before the worker begins travel for a full automated refund to your source payment account. "
            "To cancel, open Booking Details and tap 'Cancel Booking'."
        ),
        "ta": (
            "தொழிலாளர் பயணத்தைத் தொடங்குவதற்கு முன் ரத்து செய்தால், முழு பணமும் தானாகவே உங்கள் வங்கிக் கணக்கிற்குத் திருப்பித் தரப்படும்."
        ),
        "suggestions": [
            "How to book a service?",
            "Payment & UPI options",
            "Emergency service",
        ],
    },
]

DEFAULT_EN = (
    "I am the Cooperative Gig Services Assistant. I can help you with booking services, "
    "tracking workers, payment methods, cooperative welfare, and AI matching rules. How can I assist you today?"
)
DEFAULT_TA = (
    "வணக்கம்! நான் கூட்டுறவு சேவை உதவியாளர். சேவை முன்பதிவு, கட்டண முறைகள், தொழிலாளர் சரிபார்ப்பு மற்றும் "
    "கூட்டுறவு நலத்திட்டங்கள் குறித்து உங்களுக்கு வழிகாட்ட முடியும். உங்களுக்கு எவ்வாறு உதவ வேண்டும்?"
)

DEFAULT_SUGGESTIONS = [
    "How to book a service?",
    "Emergency service",
    "Payment & UPI options",
    "How ML matching works?",
    "Worker verification & KYC",
    "Cooperative welfare benefits",
]


@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat_query(request: ChatRequest) -> ChatResponse:
    """
    Process incoming user message, detect intent, and return intelligent answer with suggestions.
    """
    msg_lower = request.message.lower().strip()
    is_tamil = request.language == "ta" or any('\u0b80' <= c <= '\u0bff' for c in request.message)

    # Keyword intent matching with word boundary support
    import re
    matched_entry = None
    for entry in FAQ_KNOWLEDGE_BASE:
        for kw in entry["keywords"]:
            pattern = rf"\b{re.escape(kw)}\b" if kw.isascii() else re.escape(kw)
            if re.search(pattern, msg_lower):
                matched_entry = entry
                break
        if matched_entry:
            break

    if matched_entry:
        response_text = matched_entry["ta"] if is_tamil else matched_entry["en"]
        return ChatResponse(
            response=response_text,
            source="knowledge_base",
            intent=matched_entry["intent"],
            suggestions=matched_entry["suggestions"],
            session_id=request.session_id,
        )

    # Default fallback
    return ChatResponse(
        response=DEFAULT_TA if is_tamil else DEFAULT_EN,
        source="default_assistant",
        intent="general_help",
        suggestions=DEFAULT_SUGGESTIONS,
        session_id=request.session_id,
    )

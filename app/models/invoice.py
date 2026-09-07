from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class InvoiceResponse(BaseModel):
    id: str
    booking_id: str
    invoice_number: str
    customer_id: str
    customer_name: Optional[str] = None
    cooperative_name: Optional[str] = None
    service_name: str
    service_date: datetime
    worker_count: int = 1
    unit_price: float
    total_amount: float
    currency: str = "INR"
    invoice_status: str = "GENERATED"
    payment_id: Optional[str] = None
    generated_at: datetime
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class InvoiceDownloadResponse(BaseModel):
    invoice_number: str
    html_content: str
    file_name: str

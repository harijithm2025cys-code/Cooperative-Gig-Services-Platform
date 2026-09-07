-- PHASE 4: REAL-TIME OPERATIONS, NOTIFICATIONS, GPS/ETA & EMERGENCY BOOKING SCHEMA
-- Cooperative Gig Services Platform

-- 1. In-App Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) NOT NULL DEFAULT 'SYSTEM',
    reference_id VARCHAR(255),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Real-Time Event Audit Logs Table
CREATE TABLE IF NOT EXISTS realtime_event_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,
    booking_id UUID REFERENCES bookings(id) ON DELETE CASCADE,
    actor_id UUID,
    actor_role VARCHAR(50),
    title VARCHAR(255),
    description TEXT,
    data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Emergency Dispatches Table
CREATE TABLE IF NOT EXISTS emergency_dispatches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    priority_level VARCHAR(50) NOT NULL DEFAULT 'critical_24_7',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dispatched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_time_seconds INT DEFAULT 12,
    is_sla_met BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Worker Live Tracking and Booking SLA Extensions
ALTER TABLE IF EXISTS bookings
    ADD COLUMN IF NOT EXISTS is_emergency BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;

-- 5. Indexes for High Performance Real-Time Queries
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_realtime_events_booking ON realtime_event_logs(booking_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_emergency_dispatches_booking ON emergency_dispatches(booking_id);

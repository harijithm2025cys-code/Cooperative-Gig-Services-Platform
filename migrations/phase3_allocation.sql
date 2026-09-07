-- PHASE 3: WORKER AVAILABILITY, AUTOMATIC ALLOCATION & GEO-LOCATION SCHEMA
-- Cooperative Gig Services Platform

-- 1. Worker Availability & Proximity Extensions
ALTER TABLE IF EXISTS workers 
    ADD COLUMN IF NOT EXISTS service_radius_km DOUBLE PRECISION DEFAULT 15.0,
    ADD COLUMN IF NOT EXISTS availability_status VARCHAR(50) DEFAULT 'available',
    ADD COLUMN IF NOT EXISTS certifications JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS location_updated_at TIMESTAMPTZ DEFAULT NOW();

-- 2. Booking Multi-Worker & Allocation Tracking
ALTER TABLE IF EXISTS bookings
    ADD COLUMN IF NOT EXISTS required_worker_count INT DEFAULT 1,
    ADD COLUMN IF NOT EXISTS assigned_worker_count INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS allocation_status VARCHAR(50) DEFAULT 'REQUESTED';

-- 3. Booking Assignments Table (One Booking -> Multiple Workers)
CREATE TABLE IF NOT EXISTS booking_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    worker_id UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'ASSIGNED',
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    distance_km DOUBLE PRECISION,
    matching_score DOUBLE PRECISION,
    assignment_sequence INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_booking_worker UNIQUE (booking_id, worker_id)
);

-- 4. Matching Audit Logs (Deterministic Auditing for Association Heads & Admins)
CREATE TABLE IF NOT EXISTS matching_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    worker_id UUID REFERENCES workers(id) ON DELETE SET NULL,
    is_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    rejection_reason VARCHAR(255),
    distance_km DOUBLE PRECISION,
    matching_score DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Indexes for Fast Matching & Concurrency Lookups
CREATE INDEX IF NOT EXISTS idx_workers_skill_status ON workers(skill, is_available);
CREATE INDEX IF NOT EXISTS idx_workers_cooperative ON workers(cooperative_id);
CREATE INDEX IF NOT EXISTS idx_assignments_worker_status ON booking_assignments(worker_id, status);
CREATE INDEX IF NOT EXISTS idx_assignments_booking ON booking_assignments(booking_id);
CREATE INDEX IF NOT EXISTS idx_matching_logs_booking ON matching_logs(booking_id);

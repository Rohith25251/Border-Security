-- ==============================================================================
-- IBVAP (Intelligent Border Video Analytics Platform)
-- Supabase Database Schema & Storage Configuration
-- ==============================================================================

-- 1. Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Create the `alerts` Table
CREATE TABLE IF NOT EXISTS public.alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id TEXT NOT NULL,
    camera_name TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'intrusion',
            'anpr',
            'loitering',
            'fast_movement',
            'group_clustering',
            'face_detected',
            'night_mode_change'
        )
    ),
    object_type TEXT NOT NULL CHECK (
        object_type IN ('human', 'vehicle', 'n/a')
    ),
    license_plate TEXT,
    track_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.0,
    location TEXT NOT NULL,
    image_path TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new' CHECK (
        status IN ('new', 'acknowledged', 'resolved')
    ),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Create Performance Indices for Fast Dashboard & API Querying
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON public.alerts (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_camera_id ON public.alerts (camera_id);
CREATE INDEX IF NOT EXISTS idx_alerts_event_type ON public.alerts (event_type);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON public.alerts (status);
CREATE INDEX IF NOT EXISTS idx_alerts_track_id ON public.alerts (track_id);

-- 4. Enable Supabase Realtime for instant frontend alert broadcasting
ALTER PUBLICATION supabase_realtime ADD TABLE public.alerts;

-- 5. Row Level Security (RLS) Configuration
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;

-- Allow public/authenticated read and insert for the surveillance system
CREATE POLICY "Allow public read access to alerts"
    ON public.alerts
    FOR SELECT
    USING (true);

CREATE POLICY "Allow public insert to alerts"
    ON public.alerts
    FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Allow public update to alerts"
    ON public.alerts
    FOR UPDATE
    USING (true)
    WITH CHECK (true);

-- 6. Supabase Storage Setup for Alert Screenshots (Bucket: `alert-images`)
INSERT INTO storage.buckets (id, name, public)
VALUES ('alert-images', 'alert-images', true)
ON CONFLICT (id) DO NOTHING;

-- Public Storage Read Policy
CREATE POLICY "Public Read Access for alert-images"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'alert-images');

-- Public Storage Upload Policy
CREATE POLICY "Public Upload Access for alert-images"
    ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'alert-images');

CREATE POLICY "Public Update Access for alert-images"
    ON storage.objects FOR UPDATE
    USING (bucket_id = 'alert-images');

-- ==============================================================================
-- IBVAP (Intelligent Border Video Analytics Platform)
-- Supabase Database Schema & Storage Configuration / Migration Script
-- Run this script in the Supabase SQL Editor (Dashboard -> SQL Editor -> New Query)
-- ==============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Create the `alerts` Table (if starting fresh)
CREATE TABLE IF NOT EXISTS public.alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id TEXT NOT NULL,
    camera_name TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    object_type TEXT NOT NULL DEFAULT 'n/a',
    license_plate TEXT,
    track_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.0,
    location TEXT NOT NULL DEFAULT 'Border Sector',
    image_path TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Migration: Update Existing Columns & Drop Restrictive Check Constraints
-- (Safe to run even if table was created previously)
ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS image_path TEXT DEFAULT '';
ALTER TABLE public.alerts ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Drop old check constraints if they exist to prevent insertion rejection
ALTER TABLE public.alerts DROP CONSTRAINT IF EXISTS alerts_event_type_check;
ALTER TABLE public.alerts DROP CONSTRAINT IF EXISTS alerts_object_type_check;
ALTER TABLE public.alerts DROP CONSTRAINT IF EXISTS alerts_status_check;

-- Add updated and versatile constraints
ALTER TABLE public.alerts ADD CONSTRAINT alerts_event_type_check 
    CHECK (
        event_type IN (
            'intrusion',
            'tripwire_cross',
            'zone_intrusion',
            'anpr',
            'anpr_detected',
            'loitering',
            'fast_movement',
            'group_clustering',
            'face_detected',
            'night_mode_change'
        )
    );

ALTER TABLE public.alerts ADD CONSTRAINT alerts_status_check 
    CHECK (
        status IN ('new', 'acknowledged', 'resolved')
    );

-- 4. Create Performance Indices for Fast Dashboard & Realtime Queries
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON public.alerts (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_camera_id ON public.alerts (camera_id);
CREATE INDEX IF NOT EXISTS idx_alerts_event_type ON public.alerts (event_type);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON public.alerts (status);
CREATE INDEX IF NOT EXISTS idx_alerts_track_id ON public.alerts (track_id);
CREATE INDEX IF NOT EXISTS idx_alerts_metadata ON public.alerts USING GIN (metadata);

-- 5. Enable Supabase Realtime for Instant Frontend Alert Broadcasting
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' 
          AND schemaname = 'public' 
          AND tablename = 'alerts'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.alerts;
    END IF;
END $$;

-- 6. Row Level Security (RLS) Configuration for `alerts`
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'alerts' AND policyname = 'Allow public read access to alerts') THEN
        CREATE POLICY "Allow public read access to alerts" ON public.alerts FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'alerts' AND policyname = 'Allow public insert to alerts') THEN
        CREATE POLICY "Allow public insert to alerts" ON public.alerts FOR INSERT WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'alerts' AND policyname = 'Allow public update to alerts') THEN
        CREATE POLICY "Allow public update to alerts" ON public.alerts FOR UPDATE USING (true) WITH CHECK (true);
    END IF;
END $$;

-- 7. Supabase Storage Setup for Alert Screenshots (Bucket: `alert-images`)
INSERT INTO storage.buckets (id, name, public)
VALUES ('alert-images', 'alert-images', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- Storage RLS Policies for `alert-images` Bucket
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'objects' AND policyname = 'Public Read Access for alert-images') THEN
        CREATE POLICY "Public Read Access for alert-images"
            ON storage.objects FOR SELECT
            USING (bucket_id = 'alert-images');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'objects' AND policyname = 'Public Upload Access for alert-images') THEN
        CREATE POLICY "Public Upload Access for alert-images"
            ON storage.objects FOR INSERT
            WITH CHECK (bucket_id = 'alert-images');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'objects' AND policyname = 'Public Update Access for alert-images') THEN
        CREATE POLICY "Public Update Access for alert-images"
            ON storage.objects FOR UPDATE
            USING (bucket_id = 'alert-images');
    END IF;
END $$;

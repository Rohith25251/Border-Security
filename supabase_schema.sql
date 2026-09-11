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

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'objects' AND policyname = 'Public Delete Access for alert-images') THEN
        CREATE POLICY "Public Delete Access for alert-images"
            ON storage.objects FOR DELETE
            USING (bucket_id = 'alert-images');
    END IF;
END $$;

-- ==============================================================================
-- 8. Persons of Interest (POI) & Facial Recognition Table
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.persons_of_interest (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id TEXT,
    name TEXT NOT NULL DEFAULT 'Unidentified Subject',
    dob TEXT DEFAULT '',
    description TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    camera_id TEXT DEFAULT 'camera1',
    camera_name TEXT DEFAULT 'Camera 1',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    threat_level TEXT DEFAULT 'Suspicious',
    face_image_url TEXT,
    full_image_url TEXT,
    detected_objects JSONB DEFAULT '[]'::jsonb,
    facial_features JSONB DEFAULT '{}'::jsonb,
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Migration columns if table already existed
ALTER TABLE public.persons_of_interest ADD COLUMN IF NOT EXISTS dob TEXT DEFAULT '';
ALTER TABLE public.persons_of_interest ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE public.persons_of_interest ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';

-- Performance indices for Persons of Interest
CREATE INDEX IF NOT EXISTS idx_poi_timestamp ON public.persons_of_interest (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_poi_person_id ON public.persons_of_interest (person_id);
CREATE INDEX IF NOT EXISTS idx_poi_threat_level ON public.persons_of_interest (threat_level);
CREATE INDEX IF NOT EXISTS idx_poi_camera_id ON public.persons_of_interest (camera_id);
CREATE INDEX IF NOT EXISTS idx_poi_detected_objects ON public.persons_of_interest USING GIN (detected_objects);

-- Realtime publication for Persons of Interest
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' 
          AND schemaname = 'public' 
          AND tablename = 'persons_of_interest'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.persons_of_interest;
    END IF;
END $$;

-- Row Level Security (RLS) for `persons_of_interest`
ALTER TABLE public.persons_of_interest ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'persons_of_interest' AND policyname = 'Allow public read access to persons_of_interest') THEN
        CREATE POLICY "Allow public read access to persons_of_interest" ON public.persons_of_interest FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'persons_of_interest' AND policyname = 'Allow public insert to persons_of_interest') THEN
        CREATE POLICY "Allow public insert to persons_of_interest" ON public.persons_of_interest FOR INSERT WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'persons_of_interest' AND policyname = 'Allow public update to persons_of_interest') THEN
        CREATE POLICY "Allow public update to persons_of_interest" ON public.persons_of_interest FOR UPDATE USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'persons_of_interest' AND policyname = 'Allow public delete to persons_of_interest') THEN
        CREATE POLICY "Allow public delete to persons_of_interest" ON public.persons_of_interest FOR DELETE USING (true);
    END IF;
END $$;

-- ==============================================================================
-- 9. Supabase Storage Setup for Persons of Interest & Faces (Bucket: `person-records`)
-- ==============================================================================
INSERT INTO storage.buckets (id, name, public)
VALUES ('person-records', 'person-records', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- Storage RLS Policies for `person-records` Bucket (Read, Upload, Update, Delete)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'objects' AND policyname = 'Public Read Access for person-records') THEN
        CREATE POLICY "Public Read Access for person-records"
            ON storage.objects FOR SELECT
            USING (bucket_id = 'person-records');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'objects' AND policyname = 'Public Upload Access for person-records') THEN
        CREATE POLICY "Public Upload Access for person-records"
            ON storage.objects FOR INSERT
            WITH CHECK (bucket_id = 'person-records');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'objects' AND policyname = 'Public Update Access for person-records') THEN
        CREATE POLICY "Public Update Access for person-records"
            ON storage.objects FOR UPDATE
            USING (bucket_id = 'person-records');
    END IF;

-- ==============================================================================
-- 10. Dedicated Cameras Table for IP & RTSP Camera Management
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.cameras (
    id TEXT PRIMARY KEY,                       -- e.g. 'camera1', 'cam_192_168_1_50'
    name TEXT NOT NULL,                        -- e.g. 'Camera 1 - Border Daytime'
    ip_address TEXT DEFAULT '',                -- e.g. '192.168.1.50'
    rtsp_url TEXT NOT NULL,                    -- e.g. 'http://192.168.1.50:8080/video' or 'rtsp://...'
    fallback_file TEXT DEFAULT '',             -- e.g. 'videos/camera1_daytime.mp4'
    location TEXT NOT NULL DEFAULT 'Sector A', -- e.g. 'North Perimeter Gate'
    frame_skip INTEGER NOT NULL DEFAULT 2,
    conf_threshold REAL NOT NULL DEFAULT 0.25,
    enable_face_detection BOOLEAN NOT NULL DEFAULT true,
    enable_anpr BOOLEAN NOT NULL DEFAULT true,
    enable_night_mode BOOLEAN NOT NULL DEFAULT true,
    fences JSONB DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',     -- 'active', 'offline', 'disabled'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indices for cameras table
CREATE INDEX IF NOT EXISTS idx_cameras_status ON public.cameras (status);
CREATE INDEX IF NOT EXISTS idx_cameras_location ON public.cameras (location);

-- Enable Supabase Realtime for instant camera additions & telemetry
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' 
          AND schemaname = 'public' 
          AND tablename = 'cameras'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.cameras;
    END IF;
END $$;

-- Row Level Security (RLS) for `cameras`
ALTER TABLE public.cameras ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'cameras' AND policyname = 'Allow public read access to cameras') THEN
        CREATE POLICY "Allow public read access to cameras" ON public.cameras FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'cameras' AND policyname = 'Allow public insert to cameras') THEN
        CREATE POLICY "Allow public insert to cameras" ON public.cameras FOR INSERT WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'cameras' AND policyname = 'Allow public update to cameras') THEN
        CREATE POLICY "Allow public update to cameras" ON public.cameras FOR UPDATE USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'cameras' AND policyname = 'Allow public delete to cameras') THEN
        CREATE POLICY "Allow public delete to cameras" ON public.cameras FOR DELETE USING (true);
    END IF;
END $$;



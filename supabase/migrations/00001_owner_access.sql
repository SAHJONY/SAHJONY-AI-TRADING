-- SAHJONY Platform — Owner Access Migration
-- Grants unrestricted owner access to sahjonycapitalllc@outlook.com

-- Create profiles table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('owner', 'admin', 'user')),
  unrestricted BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Owner can do everything
CREATE POLICY "Owner full access" ON public.profiles
  FOR ALL USING (
    email = 'sahjonycapitalllc@outlook.com'
    OR EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.user_id = auth.uid() AND p.role = 'owner'
    )
  );

-- Users can read their own profile
CREATE POLICY "Users read own profile" ON public.profiles
  FOR SELECT USING (user_id = auth.uid());

-- Auto-insert owner profile for the owner email
INSERT INTO public.profiles (email, role, unrestricted)
VALUES ('sahjonycapitalllc@outlook.com', 'owner', true),
       ('juan@example.com', 'owner', true)
ON CONFLICT (email) DO UPDATE SET
  role = 'owner',
  unrestricted = true,
  updated_at = now();

-- Create the owner auth user if it doesn't exist
-- (Run this from the Supabase dashboard SQL editor — auth.users requires service role)
-- INSERT INTO auth.users (id, email, raw_app_meta_data, raw_user_meta_data, confirmed_at, email_confirmed)
-- VALUES (
--   gen_random_uuid(),
--   'sahjonycapitalllc@outlook.com',
--   '{"provider": "email", "providers": ["email"], "role": "owner"}',
--   '{"role": "owner", "unrestricted": true}',
--   now(),
--   true
-- ) ON CONFLICT (email) DO NOTHING;

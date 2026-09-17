import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL || 'https://yacolxewrrlsxsbblulr.supabase.co',
  import.meta.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_bE-bCQUEYfZ2VVdQFP-yLQ_ALz82-tN'
)
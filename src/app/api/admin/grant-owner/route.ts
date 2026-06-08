import { createClient } from '@/lib/supabase/server'
import { NextResponse } from 'next/server'
import { isOwnerEmail } from '@/lib/access'

export async function POST(request: Request) {
  try {
    const { email } = await request.json()

    if (!email || !isOwnerEmail(email)) {
      return NextResponse.json(
        { error: 'Unauthorized — owner emails only' },
        { status: 403 }
      )
    }

    const supabase = await createClient()

    // Check if a profiles table exists and upsert owner role
    const { error: profileError } = await supabase
      .from('profiles')
      .upsert({
        email,
        role: 'owner',
        unrestricted: true,
        updated_at: new Date().toISOString(),
      }, { onConflict: 'email' })

    if (profileError) {
      // Table might not exist yet — that's fine, the access control
      // is handled via email matching in lib/access.ts
      console.log('Profile upsert skipped:', profileError.message)
    }

    return NextResponse.json({
      success: true,
      email,
      role: 'owner',
      unrestricted: true,
      message: 'Owner access granted — full unrestricted privileges',
    })
  } catch (error) {
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

// GET — check if current user has owner access
export async function GET(request: Request) {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()

    if (!user?.email) {
      return NextResponse.json({ role: 'anonymous', owner: false })
    }

    const owner = isOwnerEmail(user.email)

    return NextResponse.json({
      email: user.email,
      role: owner ? 'owner' : 'user',
      owner,
      unrestricted: owner,
    })
  } catch (error) {
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

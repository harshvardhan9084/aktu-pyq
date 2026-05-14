import { NextRequest, NextResponse } from 'next/server'
import { createHash } from 'crypto'

function sha256(text: string): string {
  return createHash('sha256').update(text).digest('hex')
}
// ... (keep your imports)

export async function POST(req: NextRequest) {
  const { password } = await req.json()
  const expectedHash = process.env.ADMIN_PASSWORD_HASH

  if (!expectedHash) return NextResponse.json({ error: 'Admin not configured' }, { status: 500 })

  if (sha256(password) !== expectedHash) {
    return NextResponse.json({ error: 'Invalid password' }, { status: 401 })
  }

  // This is the token the backend expects
  const sessionToken = sha256(expectedHash + 'session_salt_aktu_pyq')

  const response = NextResponse.json({ ok: true, token: sessionToken })
  
  // We keep the cookie for the /api/admin/verify check
  response.cookies.set('admin_session', sessionToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    maxAge: 60 * 60 * 8,
    path: '/',
  })

  return response
}
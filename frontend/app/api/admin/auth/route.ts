import { NextRequest, NextResponse } from 'next/server'
import { createHash } from 'crypto'

function sha256(text: string): string {
  return createHash('sha256').update(text).digest('hex')
}

export async function POST(req: NextRequest) {
  const { password } = await req.json()
  const expectedHash = process.env.ADMIN_PASSWORD_HASH

  if (!expectedHash) {
    return NextResponse.json({ error: 'Admin not configured' }, { status: 500 })
  }

  if (sha256(password) !== expectedHash) {
    await new Promise(r => setTimeout(r, 800))
    return NextResponse.json({ error: 'Invalid password' }, { status: 401 })
  }

  // MUST match getExpectedToken() in admin-auth.ts:
  // sha256( ADMIN_PASSWORD_HASH + salt )
  const sessionToken = sha256(expectedHash + 'session_salt_aktu_pyq')
  
  const response = NextResponse.json({ ok: true, token: sessionToken })
  response.cookies.set('admin_session', sessionToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    maxAge: 60 * 60 * 8,
    path: '/',
  })
  return response
}

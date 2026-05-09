import { NextRequest, NextResponse } from 'next/server'
import { createHash } from 'crypto'

function getExpectedToken(): string {
  const hash = process.env.ADMIN_PASSWORD_HASH ?? ''
  return createHash('sha256').update(hash + 'session_salt_aktu_pyq').digest('hex')
}

export function isAdminAuthenticated(req: NextRequest): boolean {
  return req.cookies.get('admin_session')?.value === getExpectedToken()
}

export async function GET(req: NextRequest) {
  if (!isAdminAuthenticated(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  return NextResponse.json({ ok: true })
}

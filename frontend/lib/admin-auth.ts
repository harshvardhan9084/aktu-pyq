import { NextRequest } from 'next/server'
import { createHash } from 'crypto'

function getExpectedToken(): string {
  const hash = process.env.ADMIN_PASSWORD_HASH ?? ''
  return createHash('sha256').update(hash + 'session_salt_aktu_pyq').digest('hex')
}

export function isAdminAuthenticated(req: NextRequest): boolean {
  return req.cookies.get('admin_session')?.value === getExpectedToken()
}

import { NextRequest } from 'next/server'
import { createHash } from 'crypto'

function getExpectedToken(): string {
  return createHash('sha256')
    .update((process.env.ADMIN_PASSWORD_HASH ?? '') + 'session_salt_aktu_pyq')
    .digest('hex')
}

export function isAdminAuthenticated(req: NextRequest): boolean {
  return req.cookies.get('admin_session')?.value === getExpectedToken()
}

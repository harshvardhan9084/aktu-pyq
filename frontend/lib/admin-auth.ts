import { NextRequest } from 'next/server'
import { createHash } from 'crypto'

function getExpectedToken(): string {
  const hash = process.env.ADMIN_PASSWORD_HASH ?? ''
  console.log("SALT from env:", process.env.SESSION_SALT);
  console.log("HASH from env:", process.env.ADMIN_PASSWORD_HASH);
  return createHash('sha256').update(hash + 'session_salt_aktu_pyq').digest('hex')
}

export function isAdminAuthenticated(req: NextRequest): boolean {
  console.log("Received token:", req.cookies.get('admin_session')?.value);
  console.log("Expected token:", getExpectedToken());
  console.log("Match result:", req.cookies.get('admin_session')?.value === getExpectedToken());
  return req.cookies.get('admin_session')?.value === getExpectedToken()
}

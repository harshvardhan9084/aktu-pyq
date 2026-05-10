import { NextRequest } from 'next/server'
import { createHash } from 'crypto'

function getExpectedToken(): string {
  // Use the salt from env or fall back to your hardcoded string
  const salt = process.env.SESSION_SALT || 'session_salt_aktu_pyq';
  const passwordHash = process.env.ADMIN_PASSWORD || '';
  
  return createHash('sha256')
    .update(passwordHash + salt)
    .digest('hex');
}

export async function isAdminAuthenticated(req: NextRequest): Promise<boolean> {
  const adminSessionCookie = req.cookies.get("admin_session");
  const receivedToken = adminSessionCookie?.value;

  if (!receivedToken) {
    return false;
  }

  const expectedToken = getExpectedToken();
  
  // Optional: Logging for debugging (remove in production)
  // console.log("Match result:", receivedToken === expectedToken);

  return receivedToken === expectedToken;
}

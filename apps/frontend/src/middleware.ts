// Auth disabled for development - Gun Del Sol doesn't need authentication for local use
import { NextRequest, NextResponse } from 'next/server';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export default function middleware(_req: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [
    '/((?!_next|[^?]*\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)'
  ]
};

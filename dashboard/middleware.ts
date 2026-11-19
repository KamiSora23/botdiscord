import { NextResponse, type NextRequest } from "next/server";

// Sin cookie de sesión, las páginas privadas van directo al login de Discord y vuelven aquí.
export function middleware(request: NextRequest) {
  if (!request.cookies.get("nexus_session")) {
    const next = request.nextUrl.pathname + request.nextUrl.search;
    const url = new URL("/login", request.url);
    url.searchParams.set("next", next);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/account/:path*"],
};

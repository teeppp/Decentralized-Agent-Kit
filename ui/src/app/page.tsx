import HomeClient from './page.client';

export const dynamic = 'force-dynamic';

// This is a Server Component
export default function Page() {
    // Read environment variable at runtime
    // We check both NEXT_PUBLIC_REQUIRE_AUTH and REQUIRE_AUTH to be robust
    const requireAuth = process.env.NEXT_PUBLIC_REQUIRE_AUTH === 'true' || process.env.REQUIRE_AUTH === 'true';

    console.log('Server-side auth check:', {
        NEXT_PUBLIC_REQUIRE_AUTH: process.env.NEXT_PUBLIC_REQUIRE_AUTH,
        REQUIRE_AUTH: process.env.REQUIRE_AUTH,
        result: requireAuth
    });

    return <HomeClient requireAuth={requireAuth} />;
}

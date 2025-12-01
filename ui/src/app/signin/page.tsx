import SignInClient from './page.client';

export const dynamic = 'force-dynamic';

// This is a Server Component
export default function SignInPage() {
    // Read environment variables at runtime
    const hasLocalAuth = process.env.NEXT_PUBLIC_HAS_LOCAL_AUTH === 'true';
    const hasGoogleAuth = process.env.NEXT_PUBLIC_HAS_GOOGLE_AUTH === 'true';
    const hasGitHubAuth = process.env.NEXT_PUBLIC_HAS_GITHUB_AUTH === 'true';

    return (
        <SignInClient
            hasLocalAuth={hasLocalAuth}
            hasGoogleAuth={hasGoogleAuth}
            hasGitHubAuth={hasGitHubAuth}
        />
    );
}

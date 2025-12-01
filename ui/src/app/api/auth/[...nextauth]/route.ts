import NextAuth, { NextAuthOptions, DefaultSession } from 'next-auth';
import GoogleProvider from 'next-auth/providers/google';
import GitHubProvider from 'next-auth/providers/github';
import AzureADProvider from 'next-auth/providers/azure-ad';
import CredentialsProvider from 'next-auth/providers/credentials';

export const authOptions: NextAuthOptions = {
    providers: [
        // Local Credentials Provider
        CredentialsProvider({
            name: 'Credentials',
            credentials: {
                username: { label: "Username", type: "text" },
                password: { label: "Password", type: "password" }
            },
            async authorize(credentials) {
                if (!credentials?.username || !credentials?.password) {
                    return null;
                }

                const localUsers = process.env.LOCAL_AUTH_USERS || 'admin:admin123';
                const users = localUsers.split(',').map(u => {
                    const [username, password] = u.split(':');
                    return { username, password };
                });

                const user = users.find(u => u.username === credentials.username && u.password === credentials.password);

                if (user) {
                    return {
                        id: user.username,
                        name: user.username,
                        email: `${user.username}@local`,
                    };
                }

                return null;
            }
        }),
        // OAuth Providers
        GoogleProvider({
            clientId: process.env.GOOGLE_CLIENT_ID || '',
            clientSecret: process.env.GOOGLE_CLIENT_SECRET || '',
        }),
        GitHubProvider({
            clientId: process.env.GITHUB_CLIENT_ID || '',
            clientSecret: process.env.GITHUB_CLIENT_SECRET || '',
        }),
        AzureADProvider({
            clientId: process.env.AZURE_AD_CLIENT_ID || '',
            clientSecret: process.env.AZURE_AD_CLIENT_SECRET || '',
            tenantId: process.env.AZURE_AD_TENANT_ID || '',
        }),
    ],
    callbacks: {
        async jwt({ token, user, account }) {
            if (user) {
                token.userId = user.id;
                token.provider = account?.provider || 'credentials';
            }
            return token;
        },
        async session({ session, token }) {
            if (session.user) {
                session.user.id = token.userId;
                session.user.provider = token.provider;
            }
            return session;
        },
    },
    pages: {
        signIn: '/signin',
    },
    session: {
        strategy: 'jwt',
    },
    secret: process.env.NEXTAUTH_SECRET,
};

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };

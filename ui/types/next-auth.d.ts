import { DefaultSession, DefaultUser } from "next-auth"
import { JWT, DefaultJWT } from "next-auth/jwt"

declare module "next-auth" {
    interface Session extends DefaultSession {
        user: {
            id: string
            provider: string
        } & DefaultSession["user"]
    }

    interface User extends DefaultUser {
        provider?: string
    }
}

declare module "next-auth/jwt" {
    interface JWT extends DefaultJWT {
        userId: string
        provider: string
    }
}

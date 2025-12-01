import { NextResponse } from 'next/server';

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const headers: HeadersInit = {
            'Content-Type': 'application/json',
        };

        // Forward auth headers if present
        const authHeader = req.headers.get('Authorization');
        if (authHeader) {
            headers['Authorization'] = authHeader;
        }

        const userId = req.headers.get('X-User-ID');
        if (userId) {
            headers['X-User-ID'] = userId;
        }

        const sessionId = req.headers.get('X-Session-ID');
        if (sessionId) {
            headers['X-Session-ID'] = sessionId;
        }

        const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL || 'http://localhost:8000';

        const response = await fetch(`${agentUrl}/run`, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
        });

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error('Error proxying to agent:', error);
        return NextResponse.json(
            { error: 'Failed to communicate with agent' },
            { status: 500 }
        );
    }
}

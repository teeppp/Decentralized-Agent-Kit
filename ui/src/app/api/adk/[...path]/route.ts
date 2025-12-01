import { NextRequest, NextResponse } from 'next/server';

const AGENT_URL = process.env.AGENT_URL || 'http://localhost:8000';

async function proxyRequest(req: NextRequest, { params }: { params: { path: string[] } }) {
    const path = (await params).path.join('/');
    const url = `${AGENT_URL}/${path}`;

    // Get request body if applicable
    let body;
    if (req.method !== 'GET' && req.method !== 'HEAD') {
        try {
            body = await req.text();
        } catch (e) {
            // No body
        }
    }

    // Copy headers
    const headers = new Headers();
    req.headers.forEach((value, key) => {
        // Skip host header to avoid issues
        if (key.toLowerCase() !== 'host') {
            headers.set(key, value);
        }
    });

    try {
        const response = await fetch(url, {
            method: req.method,
            headers,
            body,
        });

        const responseData = await response.arrayBuffer();

        const responseHeaders = new Headers();
        response.headers.forEach((value, key) => {
            responseHeaders.set(key, value);
        });

        return new NextResponse(responseData, {
            status: response.status,
            statusText: response.statusText,
            headers: responseHeaders,
        });
    } catch (error) {
        console.error('Proxy error:', error);
        return NextResponse.json({ error: 'Failed to communicate with agent' }, { status: 500 });
    }
}

export async function GET(req: NextRequest, props: any) {
    return proxyRequest(req, props);
}

export async function POST(req: NextRequest, props: any) {
    return proxyRequest(req, props);
}

export async function PUT(req: NextRequest, props: any) {
    return proxyRequest(req, props);
}

export async function DELETE(req: NextRequest, props: any) {
    return proxyRequest(req, props);
}

export async function PATCH(req: NextRequest, props: any) {
    return proxyRequest(req, props);
}

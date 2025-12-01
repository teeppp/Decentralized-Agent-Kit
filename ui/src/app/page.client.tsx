'use client';

import { useState, useEffect } from 'react';
import { useSession, signIn, signOut } from 'next-auth/react';
import { useRouter } from 'next/navigation';

import Sidebar from '../components/Sidebar';

export default function HomeClient({ requireAuth }: { requireAuth: boolean }) {
    const { data: session, status } = useSession();
    const router = useRouter();
    const [input, setInput] = useState('');
    const [messages, setMessages] = useState<{ role: string, content: string }[]>([]);
    const [loading, setLoading] = useState(false);
    const [currentSessionId, setCurrentSessionId] = useState<string>('');

    const isAuthRequired = requireAuth && !session;

    // Initialize session ID
    useEffect(() => {
        if (session?.user?.id && !currentSessionId) {
            setCurrentSessionId(`session_${session.user.id}_${Date.now()}`);
        }
    }, [session, currentSessionId]);

    // Redirect to signin if auth is required and user is not authenticated
    useEffect(() => {
        if (requireAuth && status === 'unauthenticated') {
            router.push('/signin');
        }
    }, [requireAuth, status, router]);

    const fetchSessionHistory = async (sessionId: string) => {
        if (!sessionId || !session?.user?.id) return;
        try {
            const headers: HeadersInit = { 'Content-Type': 'application/json' };
            headers['X-User-ID'] = session.user.id;

            const userId = session.user.id;
            const res = await fetch(`/api/adk/apps/dak_agent/users/${userId}/sessions/${sessionId}`, { headers });
            if (res.ok) {
                const data = await res.json();
                setMessages(data.messages || []);
            }
        } catch (error) {
            console.error('Failed to fetch history', error);
        }
    };

    const handleSelectSession = (sessionId: string) => {
        setCurrentSessionId(sessionId);
        fetchSessionHistory(sessionId);
    };

    const handleNewChat = () => {
        if (session?.user?.id) {
            const newId = `session_${session.user.id}_${Date.now()}`;
            setCurrentSessionId(newId);
            setMessages([]);
        }
    };

    // Show loading while checking auth status
    if (status === 'loading') {
        return (
            <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
                <div className="text-gray-400">Loading...</div>
            </div>
        );
    }

    // If auth is required and not authenticated, show nothing (will redirect)
    if (isAuthRequired) {
        return null;
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (isAuthRequired) {
            // Should be handled by redirect, but just in case
            return;
        }

        if (!input.trim()) return;

        const userMessage = { role: 'user', content: input };
        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setLoading(true);

        try {
            const headers: HeadersInit = {
                'Content-Type': 'application/json',
            };

            // If authenticated, include JWT token
            if (session?.user) {
                // Get the JWT token from the session
                const tokenResponse = await fetch('/api/auth/session');
                const sessionData = await tokenResponse.json();

                // Include user ID in headers
                headers['X-User-ID'] = session.user.id;
                headers['X-Session-ID'] = currentSessionId;
            }

            // Ensure session exists
            let sessionIdForRun = currentSessionId;
            try {
                const sessionCheckRes = await fetch(`/api/adk/apps/dak_agent/users/${session?.user?.id}/sessions/${currentSessionId}`, { headers });
                if (!sessionCheckRes.ok) {
                    // Create session
                    const createRes = await fetch(`/api/adk/apps/dak_agent/users/${session?.user?.id}/sessions`, {
                        method: 'POST',
                        headers,
                        body: JSON.stringify({})
                    });
                    if (!createRes.ok) {
                        throw new Error('Failed to create session');
                    }
                    const sessionData = await createRes.json();
                    if (sessionData.id) {
                        setCurrentSessionId(sessionData.id);
                        sessionIdForRun = sessionData.id;
                    }
                }
            } catch (e) {
                console.error("Session check/create failed", e);
            }

            const res = await fetch('/api/adk/run', {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    appName: 'dak_agent',
                    userId: session?.user?.id || 'unknown',
                    sessionId: sessionIdForRun,
                    newMessage: {
                        role: 'user',
                        parts: [{ text: userMessage.content }]
                    }
                }),
            });

            const data = await res.json();
            console.log('API Response Data:', JSON.stringify(data, null, 2));

            // ADK returns an array of events
            let responseText = '';
            if (Array.isArray(data)) {
                for (const event of data) {
                    if (event.content?.role === 'model') {
                        const parts = event.content.parts || [];
                        for (const part of parts) {
                            if (part.text) {
                                responseText += part.text;
                            }
                        }
                    }
                }
            } else {
                responseText = data.response || 'No response';
            }

            setMessages(prev => [...prev, { role: 'assistant', content: responseText }]);
        } catch (error) {
            console.error('Error:', error);
            setMessages(prev => [...prev, { role: 'assistant', content: 'Error communicating with agent.' }]);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gray-900 text-white flex">
            {/* Sidebar */}
            {session && (
                <Sidebar
                    currentSessionId={currentSessionId}
                    onSelectSession={handleSelectSession}
                    onNewChat={handleNewChat}
                    className="w-64 hidden md:flex"
                />
            )}

            {/* Main Content */}
            <div className="flex-1 flex flex-col h-screen">
                {/* Header */}
                <header className="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-800/50 backdrop-blur">
                    <h1 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-600">
                        DAK Agent
                    </h1>
                    <div className="flex items-center gap-4">
                        {session ? (
                            <>
                                <span className="text-sm text-gray-400">{session.user?.email}</span>
                                <button
                                    onClick={() => signOut()}
                                    className="px-3 py-1 bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded text-sm transition-all"
                                >
                                    Sign Out
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={() => signIn()}
                                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm transition-all"
                            >
                                Sign In
                            </button>
                        )}
                    </div>
                </header>

                {/* Chat Area */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {messages.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-gray-500">
                            <p className="text-lg mb-2">Welcome to DAK Agent!</p>
                            <p className="text-sm">Start a conversation or select a history item.</p>
                        </div>
                    ) : (
                        messages.map((msg, idx) => (
                            <div
                                key={idx}
                                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                <div
                                    className={`max-w-[80%] rounded-2xl p-4 ${msg.role === 'user'
                                        ? 'bg-blue-600 text-white rounded-br-none'
                                        : 'bg-gray-800 text-gray-200 rounded-bl-none border border-gray-700'
                                        }`}
                                >
                                    <p className="whitespace-pre-wrap">{msg.content}</p>
                                </div>
                            </div>
                        ))
                    )}
                    {loading && (
                        <div className="flex justify-start">
                            <div className="bg-gray-800 rounded-2xl rounded-bl-none p-4 border border-gray-700">
                                <div className="flex gap-2">
                                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" />
                                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-75" />
                                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-150" />
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Input Area */}
                <div className="p-4 border-t border-gray-700 bg-gray-800/50 backdrop-blur">
                    <form onSubmit={handleSubmit} className="max-w-4xl mx-auto gap-4 w-full">
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all text-white placeholder-gray-400"
                            placeholder="Type your message..."
                            disabled={loading || isAuthRequired}
                        />
                        <button
                            type="submit"
                            disabled={loading || isAuthRequired || !input.trim()}
                            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-xl font-medium transition-all"
                        >
                            Send
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}

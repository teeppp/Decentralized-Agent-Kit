'use client';

import { useState, useEffect } from 'react';
import { useSession } from 'next-auth/react';

interface Session {
    session_id: string;
    last_message: string;
    message_count: number;
}

interface SidebarProps {
    currentSessionId: string;
    onSelectSession: (sessionId: string) => void;
    onNewChat: () => void;
    className?: string;
}

export default function Sidebar({ currentSessionId, onSelectSession, onNewChat, className = '' }: SidebarProps) {
    const { data: session } = useSession();
    const [sessions, setSessions] = useState<Session[]>([]);
    const [loading, setLoading] = useState(false);

    const fetchSessions = async () => {
        if (!session?.user) return;
        setLoading(true);
        try {
            const headers: HeadersInit = { 'Content-Type': 'application/json' };

            // Get auth headers
            const tokenResponse = await fetch('/api/auth/session');
            const sessionData = await tokenResponse.json();
            if (sessionData?.user?.id) {
                headers['X-User-ID'] = sessionData.user.id;
            }

            const userId = sessionData.user.id;
            const res = await fetch(`/api/adk/apps/dak_agent/users/${userId}/sessions`, { headers });
            if (res.ok) {
                const data = await res.json();
                setSessions(data.sessions || []);
            }
        } catch (error) {
            console.error('Failed to fetch sessions', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchSessions();
    }, [session]);

    const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
        e.stopPropagation();
        if (!confirm('Delete this chat?')) return;

        try {
            const headers: HeadersInit = { 'Content-Type': 'application/json' };
            const tokenResponse = await fetch('/api/auth/session');
            const sessionData = await tokenResponse.json();
            if (sessionData?.user?.id) {
                headers['X-User-ID'] = sessionData.user.id;
            }

            const userId = sessionData.user.id;
            await fetch(`/api/adk/apps/dak_agent/users/${userId}/sessions/${sessionId}`, {
                method: 'DELETE',
                headers
            });

            setSessions(sessions.filter(s => s.session_id !== sessionId));
            if (currentSessionId === sessionId) {
                onNewChat();
            }
        } catch (error) {
            console.error('Failed to delete session', error);
        }
    };

    return (
        <div className={`bg-gray-800 border-r border-gray-700 flex flex-col ${className}`}>
            <div className="p-4 border-b border-gray-700">
                <button
                    onClick={onNewChat}
                    className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-medium transition-colors flex items-center justify-center gap-2"
                >
                    <span>+</span> New Chat
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-2">
                {loading ? (
                    <div className="text-center text-gray-500 py-4">Loading...</div>
                ) : sessions.length === 0 ? (
                    <div className="text-center text-gray-500 py-4">No history</div>
                ) : (
                    sessions.map((s) => (
                        <div
                            key={s.session_id}
                            onClick={() => onSelectSession(s.session_id)}
                            className={`p-3 rounded-lg cursor-pointer group flex justify-between items-start transition-colors ${currentSessionId === s.session_id
                                ? 'bg-gray-700 text-white'
                                : 'text-gray-400 hover:bg-gray-700/50 hover:text-gray-200'
                                }`}
                        >
                            <div className="flex-1 min-w-0">
                                <div className="font-medium text-sm truncate">
                                    {s.session_id}
                                </div>
                                <div className="text-xs truncate opacity-70">
                                    {s.last_message}
                                </div>
                            </div>
                            <button
                                onClick={(e) => handleDelete(e, s.session_id)}
                                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
                                title="Delete"
                            >
                                ×
                            </button>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}

"use client";

import { usePathname, useRouter } from "next/navigation";
import { Cpu, GitBranch, LayoutDashboard, MessageSquareCode, Lightbulb, BarChart3, Settings, LogOut, MessageSquare } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchApi } from "@/lib/api";

export default function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const [sessions, setSessions] = useState<any[]>([]);

  const loadSessions = () => {
    const token = typeof window !== 'undefined' && localStorage.getItem("jwt_token");
    if (!token) return;
    
    fetchApi("/chat/sessions")
      .then((res: any) => {
        if (Array.isArray(res)) {
          setSessions(res.slice(0, 15)); // Display up to 15 recent chat sessions
        }
      })
      .catch((err) => console.error("Failed to load sidebar chat sessions:", err));
  };

  useEffect(() => {
    loadSessions();

    // Listen to custom updates dispatched from the chat panel
    window.addEventListener("chat-updated", loadSessions);
    return () => {
      window.removeEventListener("chat-updated", loadSessions);
    };
  }, [pathname]);

  const handleLogout = () => {
    localStorage.removeItem("jwt_token");
    router.push("/login");
  };

  const navItems = [
    { name: "Dashboard", path: "/", icon: LayoutDashboard },
    { name: "K8s Explorer", path: "/kubernetes", icon: Cpu },
    { name: "GitHub Sync", path: "/github", icon: GitBranch },
    { name: "AI Copilot", path: "/chat", icon: MessageSquareCode },
    { name: "Suggestions", path: "/suggestions", icon: Lightbulb },
    { name: "Analytics", path: "/analytics", icon: BarChart3 },
    { name: "Integrations", path: "/integrations", icon: Settings },
  ];

  return (
    <aside className="w-64 border-r border-slate-800/50 glass-panel flex flex-col z-10 m-4 rounded-xl overflow-hidden shrink-0">
      {/* Logo Area */}
      <div className="p-6 flex items-center space-x-3 mb-4">
        <div className="text-indigo-500">
          <Cpu size={32} />
        </div>
        <div>
          <h1 className="font-bold text-lg tracking-tight leading-none text-white">Nexus AI</h1>
          <p className="text-[10px] text-slate-400 mt-1 uppercase tracking-wider">Incident Command Center</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 space-y-2 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.path;

          return (
            <Link key={item.name} href={item.path}>
              <div className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
                isActive 
                  ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 glow-primary" 
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent"
              }`}>
                <Icon size={18} />
                <span className="font-medium text-sm">{item.name}</span>
              </div>
            </Link>
          );
        })}

        {/* Recent Chats Section */}
        <div className="pt-4 border-t border-slate-800/50 mt-4 px-2">
          <Link href="/chat?new=true">
            <div className="w-full flex items-center justify-center space-x-2 px-3 py-2 mb-3 rounded-lg border border-indigo-500/30 bg-indigo-600/10 hover:bg-indigo-600/20 text-xs text-indigo-300 transition-all font-semibold cursor-pointer">
              <span>+ New Chat</span>
            </div>
          </Link>

          {sessions.length > 0 && (
            <>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-2 px-2">Recent Chats</p>
              <div className="space-y-1 max-h-56 overflow-y-auto pr-1">
                {sessions.map((session, index) => {
                  const isActive = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get("sid") === session.session_id;
                  return (
                    <Link key={index} href={`/chat?sid=${session.session_id}`}>
                      <div className={`w-full flex items-center space-x-2 px-2 py-1.5 rounded text-xs transition-all truncate cursor-pointer ${
                        isActive
                          ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/20"
                          : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                      }`}>
                        <MessageSquare size={12} className="shrink-0 text-slate-500" />
                        <span className="truncate" title={session.session_title}>{session.session_title}</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </nav>

      {/* Bottom Profile / Logout */}
      <div className="p-4 mt-auto">
        <button 
          onClick={handleLogout}
          className="w-full flex items-center space-x-3 px-4 py-3 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all"
        >
          <LogOut size={18} />
          <span className="font-medium text-sm">Logout</span>
        </button>
      </div>
    </aside>
  );
}

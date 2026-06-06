"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import DashboardLayout from "@/components/DashboardLayout";
import { MessageSquareCode, Send, Bot, User, Activity, Sun, Sunset, Moon, Paperclip } from "lucide-react";
import { fetchApi } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import dynamic from "next/dynamic";

const ExcalidrawBoard = dynamic(
  () => import("@/components/ExcalidrawBoard"),
  { ssr: false }
);

// ─── Helpers ─────────────────────────────────────────────────────────────────
function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return "Good Morning";
  if (hour >= 12 && hour < 18) return "Good Afternoon";
  return "Good Evening";
}

function getGreetingIcon() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return Sun;
  if (hour >= 12 && hour < 18) return Sunset;
  return Moon;
}

function decodeJwtPayload(token: string): Record<string, any> {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch {
    return {};
  }
}

function CodeBlock({ children, ...props }: any) {
  const [copied, setCopied] = useState(false);
  const codeRef = useRef<HTMLPreElement>(null);

  const codeChild = children && children.props ? children : (Array.isArray(children) ? children[0] : null);
  if (codeChild && codeChild.props && codeChild.props.className === "language-excalidraw") {
    try {
      const parsedElements = JSON.parse(String(codeChild.props.children).trim());
      return <ExcalidrawBoard elements={parsedElements.elements || []} />;
    } catch (e) {
      return (
        <div>
          <div className="bg-rose-950/20 border border-rose-500/30 text-rose-400 p-3 rounded-lg text-xs font-mono my-2">
            Failed to render diagram canvas. details: {String(e)}
          </div>
          <pre className="bg-[#020617] border border-white/10 rounded-lg p-4 overflow-x-auto font-mono text-xs text-slate-400 mt-2">
            {String(codeChild.props.children)}
          </pre>
        </div>
      );
    }
  }

  const handleCopy = async () => {
    if (codeRef.current) {
      const text = codeRef.current.innerText || "";
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="relative group my-2">
      <button
        onClick={handleCopy}
        className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white px-2.5 py-1 rounded text-[11px] border border-white/10 flex items-center gap-1 cursor-pointer font-sans"
      >
        {copied ? "Copied!" : "Copy"}
      </button>
      <pre
        ref={codeRef}
        className="bg-[#020617] border border-white/10 rounded-lg p-4 overflow-x-auto font-mono text-xs text-slate-300"
        {...props}
      >
        {children}
      </pre>
    </div>
  );
}

export default function AICopilot() {
  const router = useRouter();
  const pathname = usePathname();
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [sending, setSending] = useState(false);
  const [fullName, setFullName] = useState("");
  const [imageFile, setImageFile] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setImageFile(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const showDefaultWelcome = (nameStr?: string) => {
    const activeName = nameStr || fullName || "";
    const firstName = activeName.split(" ")[0];
    const greeting = getGreeting();
    const welcome = firstName
      ? `${greeting}, ${firstName}! 👋 I am the Nexus AI Copilot. I have full visibility into your active incidents and service logs. How can I assist you today?`
      : `${greeting}! I am the Nexus AI Copilot. I have full visibility into your active incidents and service logs. How can I assist you today?`;
    setMessages([{ role: "assistant", content: welcome }]);
    setSessionId(null);
    setSessionTitle(null);
  };

  const loadActiveSession = (sid: string) => {
    setLoading(true);
    setSessionId(sid);
    fetchApi(`/chat/sessions/${sid}`)
      .then((history: any) => {
        if (Array.isArray(history) && history.length > 0) {
          const title = history[0].session_title || "Recent Chat";
          setSessionTitle(title);
          
          const mapped = history.map((msg: any) => {
            let content = msg.content || "";
            if (msg.role === "user" && msg.image_base64) {
              content = `🖼️ [Uploaded Architecture Diagram] ${content}`;
            }
            return {
              role: msg.role || "assistant",
              content: content
            };
          });
          setMessages(mapped);
        } else {
          showDefaultWelcome();
        }
      })
      .catch((err) => {
        console.error("Failed to load session messages:", err);
        showDefaultWelcome();
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    const token = localStorage.getItem("jwt_token");
    if (!token) {
      router.push("/login");
      return;
    }

    // Decode full_name from JWT
    const payload = decodeJwtPayload(token);
    const name = payload.full_name || payload.email || "";
    setFullName(name);

    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const isNew = params.get("new") === "true";
      const sidParam = params.get("sid");

      if (isNew) {
        showDefaultWelcome(name);
        setLoading(false);
        // Clean query parameters from URL
        window.history.replaceState({}, "", "/chat");
        return;
      }

      if (sidParam) {
        loadActiveSession(sidParam);
        return;
      }

      // Default load: fetch sessions list and auto-load the latest session if it exists
      fetchApi("/chat/sessions")
        .then((sessions: any) => {
          if (Array.isArray(sessions) && sessions.length > 0) {
            const latestSid = sessions[0].session_id;
            window.history.replaceState({}, "", `/chat?sid=${latestSid}`);
            loadActiveSession(latestSid);
          } else {
            showDefaultWelcome(name);
            setLoading(false);
          }
        })
        .catch((err) => {
          console.error("Failed to load chat sessions:", err);
          showDefaultWelcome(name);
          setLoading(false);
        });
    }
  }, [pathname]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() && !imageFile) return;

    const userMsg = input.trim();
    const payloadQuery = userMsg || "Analyze this uploaded infrastructure architecture diagram.";
    
    // Include a visual indicator in user's chat message if they uploaded an image
    const userDisplayContent = imageFile 
      ? `🖼️ [Uploaded Architecture Diagram] ${userMsg}`
      : userMsg;

    const activeSid = sessionId || `session_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const activeTitle = sessionTitle || (userMsg.substring(0, 40) + (userMsg.length > 40 ? "..." : ""));

    if (!sessionId) {
      setSessionId(activeSid);
      setSessionTitle(activeTitle);
      setMessages([{ role: "user", content: userDisplayContent }]);
      window.history.replaceState({}, "", `/chat?sid=${activeSid}`);
    } else {
      setMessages((prev) => [...prev, { role: "user", content: userDisplayContent }]);
    }

    setInput("");
    setSending(true);

    const currentImage = imageFile;
    setImageFile(null);

    try {
      const data = await fetchApi("/chat", {
        method: "POST",
        body: JSON.stringify({ 
          query: payloadQuery, 
          time_window_mins: 60,
          image_base64: currentImage,
          session_id: activeSid,
          session_title: activeTitle
        }),
      });
      setMessages((prev) => [...prev, { role: "assistant", content: data.answer }]);
      
      // Dispatch custom event to notify sidebar of updates
      window.dispatchEvent(new Event("chat-updated"));
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `⚠️ **Error:** ${err.message}` },
      ]);
    } finally {
      setSending(false);
    }
  };

  const GreetingIcon = getGreetingIcon();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Activity className="animate-spin text-indigo-500 w-8 h-8" />
      </div>
    );
  }

  return (
    <DashboardLayout>
      <div className="flex flex-col h-[calc(100vh-6rem)]">
        {/* Header */}
        <div className="mb-6">
          <h2 className="text-xl font-medium tracking-wide text-white flex items-center">
            <MessageSquareCode className="mr-3 text-indigo-400" /> AI Copilot
          </h2>
          <p className="text-sm text-slate-500 mt-1 flex items-center gap-2">
            <GreetingIcon size={14} className="text-amber-400" />
            {getGreeting()}{fullName ? `, ${fullName.split(" ")[0]}` : ""} — powered by Amazon Bedrock · Claude 3 Haiku
          </p>
        </div>

        <div className="flex-1 glass-panel rounded-xl flex flex-col overflow-hidden relative">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500/0 via-indigo-500 to-indigo-500/0"></div>

          {/* Chat History */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} w-full max-w-full`}>
                <div className={`max-w-[85%] md:max-w-[80%] flex space-x-4 ${msg.role === "user" ? "flex-row-reverse space-x-reverse" : ""} w-full`}>
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                      msg.role === "user" ? "bg-indigo-600" : "bg-emerald-600"
                    }`}
                  >
                    {msg.role === "user" ? <User size={16} /> : <Bot size={16} />}
                  </div>
                  <div
                    className={`p-4 rounded-2xl max-w-full overflow-x-auto ${
                      msg.role === "user"
                        ? "bg-indigo-600/20 border border-indigo-500/30 text-indigo-100 whitespace-pre-wrap"
                        : "bg-black/40 border border-white/10 text-slate-300 shadow-[0_0_15px_rgba(16,185,129,0.1)] w-full"
                    }`}
                  >
                    {msg.role === "user" ? (
                      msg.content
                    ) : (
                      <div className="text-slate-300 max-w-full overflow-hidden text-sm leading-relaxed">
                        <ReactMarkdown
                          components={{
                            pre: ({ ...props }) => <CodeBlock {...props} />,
                            code: ({ ...props }) => <code className="bg-slate-800 text-indigo-300 px-1 py-0.5 rounded text-xs font-mono" {...props} />,
                            h1: ({ ...props }) => <h1 className="text-lg font-bold text-white mt-4 mb-2 first:mt-0" {...props} />,
                            h2: ({ ...props }) => <h2 className="text-md font-semibold text-white mt-3 mb-1 first:mt-0" {...props} />,
                            h3: ({ ...props }) => <h3 className="text-sm font-semibold text-slate-200 mt-2 mb-1 first:mt-0" {...props} />,
                            ul: ({ ...props }) => <ul className="list-disc pl-5 space-y-1 my-2" {...props} />,
                            ol: ({ ...props }) => <ol className="list-decimal pl-5 space-y-1 my-2" {...props} />,
                            li: ({ ...props }) => <li className="text-slate-300" {...props} />,
                            p: ({ ...props }) => <div className="mb-2 last:mb-0" {...props} />,
                            a: ({ ...props }) => <a className="text-indigo-400 hover:underline" target="_blank" rel="noopener noreferrer" {...props} />
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {sending && (
              <div className="flex justify-start">
                <div className="max-w-[80%] flex space-x-4">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-emerald-600">
                    <Bot size={16} />
                  </div>
                  <div className="p-4 rounded-2xl bg-black/40 border border-white/10 text-slate-400 flex space-x-2 items-center">
                    <div className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: "0.2s" }}></div>
                    <div className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: "0.4s" }}></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="p-4 border-t border-white/10 bg-black/20">
            {imageFile && (
              <div className="mb-3 relative w-16 h-16 border border-indigo-500/50 rounded-lg overflow-hidden group bg-slate-900 flex items-center justify-center">
                <img src={imageFile} alt="Upload preview" className="object-cover w-full h-full" />
                <button 
                  onClick={() => setImageFile(null)}
                  className="absolute inset-0 bg-black/75 opacity-0 group-hover:opacity-100 flex items-center justify-center text-rose-500 hover:text-rose-400 text-xs font-bold transition-opacity cursor-pointer border-none font-sans"
                >
                  Remove
                </button>
              </div>
            )}
            <div className="relative flex items-center bg-[#0a0a0f] border border-slate-800 rounded-xl px-4 py-2 focus-within:border-indigo-500/50 transition-all">
              <label className="mr-3 cursor-pointer text-slate-400 hover:text-white transition-colors">
                <Paperclip size={18} />
                <input 
                  type="file" 
                  accept="image/*" 
                  className="hidden" 
                  onChange={handleImageChange}
                />
              </label>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                placeholder="Ask anything or attach a diagram and type 'compile this to terraform'..."
                className="flex-1 bg-transparent text-white focus:outline-none py-2 pr-12 text-sm"
              />
              <button
                onClick={handleSend}
                disabled={sending}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-indigo-400 hover:text-indigo-300 disabled:opacity-50 transition-colors cursor-pointer"
              >
                <Send size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}

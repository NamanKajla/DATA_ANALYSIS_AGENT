import React, { useState, useEffect, useRef } from "react";
import { 
  Database, 
  MessageSquare, 
  TrendingUp, 
  Plus, 
  Trash2, 
  Upload, 
  Send, 
  ChevronRight, 
  Terminal, 
  AlertTriangle, 
  Image as ImageIcon,
  Sparkles,
  Loader2,
  FileText,
  Edit3,
  Check,
  X,
  MoreVertical,
  Code,
  Download
} from "lucide-react";

interface Session {
  id: string;
  title: string;
  created_at: string;
}

interface Dataset {
  id: string;
  file_name: string;
  schema_json: {
    columns: string[];
    dtypes: Record<string, string>;
    null_rates: Record<string, string>;
    anomalies: Record<string, string>;
    numerical_stats?: Record<string, {
      mean: string;
      median: string;
      min: string;
      max: string;
      std: string;
    }>;
    total_rows: number;
  };
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  generated_code?: string;
  chart_url?: string;
  chart_summary?: string;
  follow_ups?: string[];
  created_at: string;
}

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("workspace") || localStorage.getItem("data_agent_selected_session_id");
  });
  const [messages, setMessages] = useState<Message[]>([]);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  
  // UI states
  const [newSessionTitle, setNewSessionTitle] = useState("");
  const [question, setQuestion] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);
  const [showCodeMap, setShowCodeMap] = useState<Record<string, boolean>>({});
  
  const [showSqlModal, setShowSqlModal] = useState(false);
  const [dbType, setDbType] = useState("postgresql");
  const [dbHost, setDbHost] = useState("");
  const [dbPort, setDbPort] = useState("5432");
  const [dbName, setDbName] = useState("");
  const [dbUser, setDbUser] = useState("");
  const [dbPass, setDbPass] = useState("");
  const [dbTable, setDbTable] = useState("");
  const [isConnectingDb, setIsConnectingDb] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateInput, setShowCreateInput] = useState(false);
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [showDeleteConfirmModal, setShowDeleteConfirmModal] = useState(false);
  const [isVisualsOpen, setIsVisualsOpen] = useState(false);
  const [prevChartCount, setPrevChartCount] = useState(0);
  
  const [isEditingWorkspaceTitle, setIsEditingWorkspaceTitle] = useState(false);
  const [tempWorkspaceTitle, setTempWorkspaceTitle] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [sessionMenuId, setSessionMenuId] = useState<string | null>(null);
  const [copiedSessionId, setCopiedSessionId] = useState<string | null>(null);
  const [selectedStatsCol, setSelectedStatsCol] = useState<string | null>(null);
  const [activeNavMenu, setActiveNavMenu] = useState<"file" | "database" | "help" | null>(null);
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null);
  
  const [hoveredColumnAnomaly, setHoveredColumnAnomaly] = useState<string | null>(null);
  const [selectedDiagram, setSelectedDiagram] = useState<{
    id: string;
    chartUrl: string;
    code: string;
    summary: string;
    question: string;
  } | null>(null);
  const [zoomedChartUrl, setZoomedChartUrl] = useState<string | null>(null);
  
  const [showChartCodeMap, setShowChartCodeMap] = useState<Record<string, boolean>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const questionInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamingTimerRef = useRef<any>(null);

  const stopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (streamingTimerRef.current) {
      clearInterval(streamingTimerRef.current);
      streamingTimerRef.current = null;
    }
    setStreamingMsgId(null);
    setIsQuerying(false);
  };

  // Close session and nav dropdowns when clicking anywhere else
  useEffect(() => {
    const handleOutsideClick = () => {
      setSessionMenuId(null);
      setActiveNavMenu(null);
    };
    window.addEventListener("click", handleOutsideClick);
    return () => window.removeEventListener("click", handleOutsideClick);
  }, []);

  // Sync selected session ID to localStorage and update URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (selectedSessionId) {
      localStorage.setItem("data_agent_selected_session_id", selectedSessionId);
      if (params.get("workspace") !== selectedSessionId) {
        params.set("workspace", selectedSessionId);
        window.history.pushState(null, "", `?${params.toString()}`);
      }
    } else {
      localStorage.removeItem("data_agent_selected_session_id");
      if (params.has("workspace")) {
        params.delete("workspace");
        const newSearch = params.toString();
        window.history.pushState(null, "", newSearch ? `?${newSearch}` : window.location.pathname);
      }
    }
  }, [selectedSessionId]);

  // Load Sessions
  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      const res = await fetch(`${API_BASE}/sessions`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch (err) {
      console.error("Error fetching sessions:", err);
    }
  };

  const handleRenameSession = async (id: string, newTitle: string) => {
    try {
      const res = await fetch(`${API_BASE}/sessions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle })
      });
      if (res.ok) {
        const updated = await res.json();
        setSessions(prev => prev.map(s => s.id === id ? { ...s, title: updated.title } : s));
      }
    } catch (err) {
      console.error("Error renaming session:", err);
    }
  };

  const handleCreateSessionDirect = async () => {
    if (!newSessionTitle.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newSessionTitle })
      });
      if (res.ok) {
        const newSession = await res.json();
        setSessions(prev => [newSession, ...prev]);
        setSelectedSessionId(newSession.id);
        setNewSessionTitle("");
      }
    } catch (err) {
      console.error("Error creating session:", err);
    }
  };

  // Load session specific dataset and messages
  useEffect(() => {
    if (selectedSessionId) {
      fetchSessionData(selectedSessionId);
    } else {
      setMessages([]);
      setDataset(null);
    }
  }, [selectedSessionId]);

  // Load preview data when dataset changes
// Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isQuerying]);

  // Auto-toggle visuals pane on getting first visualization or when count increases
  useEffect(() => {
    const chartCount = messages.filter(m => !!m.chart_url).length;
    if (chartCount > prevChartCount) {
      setIsVisualsOpen(true);
    } else if (chartCount === 0) {
      setIsVisualsOpen(false);
    }
    setPrevChartCount(chartCount);
  }, [messages]);

  const fetchSessionData = async (sessionId: string) => {
    try {
      // Fetch messages
      const msgRes = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
      if (msgRes.ok) {
        const msgs: Message[] = await msgRes.json();
        setMessages(msgs);
        
        // Determine last chart url
      }

      // Fetch dataset info
      const dsRes = await fetch(`${API_BASE}/sessions/${sessionId}/dataset`);
      if (dsRes.ok) {
        const dsData = await dsRes.json();
        setDataset(dsData);
      } else {
        setDataset(null);
      }
    } catch (err) {
      console.error("Error loading session data:", err);
    }
  };

  const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this session?")) return;
    try {
      const res = await fetch(`${API_BASE}/sessions/${id}`, { method: "DELETE" });
      if (res.ok) {
        setSessions(prev => prev.filter(s => s.id !== id));
        if (selectedSessionId === id) {
          setSelectedSessionId(null);
        }
      }
    } catch (err) {
      console.error("Error deleting session:", err);
    }
  };

  const performUpload = (file: File) => {
    return new Promise<any>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/sessions/${selectedSessionId}/upload`);
      
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          setUploadProgress(percent);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.response));
          } catch (err) {
            reject(new Error("Invalid server response"));
          }
        } else {
          try {
            const err = JSON.parse(xhr.response);
            reject(new Error(err.detail || "Upload failed."));
          } catch (err) {
            reject(new Error("Upload failed."));
          }
        }
      };

      xhr.onerror = () => reject(new Error("Network connection error."));
      
      const formData = new FormData();
      formData.append("file", file);
      xhr.send(formData);
    });
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedSessionId) return;

    setIsUploading(true);
    setUploadProgress(0);

    try {
      const data = await performUpload(file);
      setDataset(data.dataset);
      fetchSessionData(selectedSessionId);
    } catch (err: any) {
      console.error("Upload error:", err);
      alert(err.message || "An error occurred during file upload.");
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleSqlConnect = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!dbHost.trim() || !dbPort.trim() || !dbName.trim() || !dbUser.trim() || !dbPass.trim() || !dbTable.trim() || !selectedSessionId) {
      alert("Please fill in all database fields.");
      return;
    }

    let connectionString = "";
    if (dbType === "postgresql") {
      connectionString = `postgresql://${dbUser}:${dbPass}@${dbHost}:${dbPort}/${dbName}`;
    } else if (dbType === "mysql") {
      connectionString = `mysql+pymysql://${dbUser}:${dbPass}@${dbHost}:${dbPort}/${dbName}`;
    }

    setIsConnectingDb(true);
    try {
      const res = await fetch(`${API_BASE}/sessions/${selectedSessionId}/connect-db`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          connection_string: connectionString,
          table_name: dbTable
        })
      });

      if (res.ok) {
        const data = await res.json();
        setDataset(data.dataset);
        fetchSessionData(selectedSessionId);
        setShowSqlModal(false);
        // Reset states
        setDbHost("");
        setDbPort(dbType === "mysql" ? "3306" : "5432");
        setDbName("");
        setDbUser("");
        setDbPass("");
        setDbTable("");
      } else {
        const errData = await res.json();
        alert(errData.detail || "Database connection failed.");
      }
    } catch (err) {
      console.error("DB connection error:", err);
      alert("An error occurred connecting to database.");
    } finally {
      setIsConnectingDb(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files?.[0];
    if (!file || !selectedSessionId) return;

    const validExts = [".csv", ".json", ".xls", ".xlsx"];
    const fileExt = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!validExts.includes(fileExt)) {
      alert("Unsupported file format. Please drop a CSV, JSON, or Excel file.");
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);

    try {
      const data = await performUpload(file);
      setDataset(data.dataset);
      fetchSessionData(selectedSessionId);
    } catch (err: any) {
      console.error("Upload error:", err);
      alert(err.message || "An error occurred during file upload.");
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
    }
  };

  const executeAnalysisQuestion = async (userQuestion: string) => {
    if (!userQuestion.trim() || !selectedSessionId || isQuerying) return;

    setIsQuerying(true);

    // Optimistically add user question to UI
    const tempUserMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: userQuestion,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, tempUserMsg]);

    // Prepend context if replying to a specific diagram
    let apiQuestion = userQuestion;
    if (selectedDiagram) {
      apiQuestion = `[Context: Regarding the chart described as "${selectedDiagram.summary}" generated by this code:\n\`\`\`python\n${selectedDiagram.code}\n\`\`\`]\n\nUser follow-up question: ${userQuestion}`;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await fetch(`${API_BASE}/sessions/${selectedSessionId}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: apiQuestion }),
        signal: controller.signal
      });

      if (res.ok) {
        const reply: Message = await res.json();
        if (!reply.id) {
          reply.id = `assistant-${Date.now()}`;
        }
        
        // ChatGPT style word-by-word streaming effect
        const fullContent = reply.content;
        const words = fullContent.split(" ");
        let currentText = "";
        let wordIdx = 0;
        
        const tempReply: Message = { ...reply, content: "" };
        setMessages(prev => [...prev, tempReply]);
        setStreamingMsgId(reply.id);
        
        streamingTimerRef.current = setInterval(() => {
          if (wordIdx < words.length) {
            currentText += (wordIdx === 0 ? "" : " ") + words[wordIdx];
            setMessages(prev => prev.map(m => m.id === reply.id ? { ...m, content: currentText } : m));
            wordIdx++;
          } else {
            if (streamingTimerRef.current) {
              clearInterval(streamingTimerRef.current);
              streamingTimerRef.current = null;
            }
            setStreamingMsgId(null);
            setSelectedDiagram(null); // Clear selected context
          }
        }, 35);
      } else {
        const errData = await res.json();
        alert(errData.detail || "Calculation execution failed.");
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        console.error("Query error:", err);
      }
    } finally {
      abortControllerRef.current = null;
      setIsQuerying(false);
    }
  };

  const handleDeleteDatasetSource = async () => {
    if (!selectedSessionId) return;
    try {
      const res = await fetch(`${API_BASE}/sessions/${selectedSessionId}/dataset`, {
        method: "DELETE"
      });
      if (res.ok) {
        setDataset(null);
        setMessages([]);
        setSelectedDiagram(null);
        setShowCodeMap({});
        setShowChartCodeMap({});
        setIsVisualsOpen(false);
      }
    } catch (err) {
      console.error("Error deleting source:", err);
    }
  };

  const handleClearWorkspaceChat = async () => {
    if (!selectedSessionId) return;
    if (!confirm("Are you sure you want to clear all messages in this workspace?")) return;
    try {
      const res = await fetch(`${API_BASE}/sessions/${selectedSessionId}/messages`, {
        method: "DELETE"
      });
      if (res.ok) {
        setMessages([]);
      }
    } catch (err) {
      console.error("Error clearing chat:", err);
    }
  };

  const handleExportChatHistory = () => {
    if (!selectedSessionId) return;
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(messages, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `chat_history_${selectedSessionId}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleAskQuestion = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    executeAnalysisQuestion(question);
    setQuestion("");
  };

  const toggleCode = (msgId: string) => {
    setShowCodeMap(prev => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  const renderMessageContent = (content: string) => {
    if (!content) return null;
    const lines = content.split("\n");
    return lines.map((line, lineIdx) => {
      const parts = line.split(/\*\*([^*]+)\*\*/g);
      return (
        <div key={lineIdx} className={lineIdx > 0 ? "mt-1.5" : ""}>
          {parts.map((part, partIdx) => {
            if (partIdx % 2 === 1) {
              return <strong key={partIdx} className="font-bold text-white">{part}</strong>;
            }
            return part;
          })}
        </div>
      );
    });
  };

  const filteredSessions = sessions.filter(s => 
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col h-screen w-screen bg-[#09090b] text-[#f4f4f5] overflow-hidden select-none relative">
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
          animation: fadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
      `}</style>
      
      {/* 1. TOP MENU BAR (Google Colab style) */}
      <div className="h-14 border-b border-[#27272a] bg-[#121214] flex items-center justify-between px-4 shrink-0 z-30">
        <div className="flex items-center gap-3">
          {/* Orange DA logo (Colab CO logo feel) - Enlarged */}
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-[#e58a2d] text-white font-extrabold text-sm select-none shadow-md">
            DA
          </div>
          <div className="flex flex-col">
            <span className="font-extrabold text-sm md:text-base text-white leading-tight tracking-wide">Data Agent Studio</span>
            <div className="flex items-center gap-5 text-sm mt-1 font-sans relative">
              {/* File Dropdown Trigger */}
              <div className="relative" onClick={(e) => e.stopPropagation()}>
                <span 
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveNavMenu(activeNavMenu === "file" ? null : "file");
                  }}
                  className={`hover:text-white cursor-pointer transition py-1 px-2.5 rounded font-bold text-sm tracking-wide ${
                    activeNavMenu === "file" ? "text-white bg-[#27272a]" : ""
                  }`}
                >
                  File
                </span>
                {activeNavMenu === "file" && (
                  <div className="absolute left-0 mt-2.5 w-56 bg-[#121214] border border-[#27272a] rounded-lg shadow-xl py-1 z-50 text-xs text-[#e4e4e7]" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedSessionId(null);
                        setActiveNavMenu(null);
                      }}
                      className="w-full text-left px-3.5 py-2.5 hover:bg-[#27272a] hover:text-white flex items-center gap-2 font-medium"
                    >
                      <ChevronRight className="w-4 h-4 rotate-180 text-zinc-400" />
                      Open Workspace...
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setNewSessionTitle("");
                        setShowCreateInput(true);
                        setSelectedSessionId(null);
                        setActiveNavMenu(null);
                      }}
                      className="w-full text-left px-3.5 py-2.5 hover:bg-[#27272a] hover:text-white flex items-center gap-2 font-medium"
                    >
                      <Plus className="w-4 h-4 text-zinc-400" />
                      New Workspace...
                    </button>
                    {selectedSessionId && (
                      <>
                        <div className="border-t border-[#27272a] my-1" />
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setTempWorkspaceTitle(sessions.find(s => s.id === selectedSessionId)?.title || "");
                            setIsEditingWorkspaceTitle(true);
                            setActiveNavMenu(null);
                          }}
                          className="w-full text-left px-3.5 py-2.5 hover:bg-[#27272a] hover:text-white flex items-center gap-2 font-medium"
                        >
                          <Edit3 className="w-4 h-4 text-zinc-400" />
                          Rename Workspace
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleExportChatHistory();
                            setActiveNavMenu(null);
                          }}
                          className="w-full text-left px-3.5 py-2.5 hover:bg-[#27272a] hover:text-white flex items-center gap-2 font-medium"
                        >
                          <FileText className="w-4 h-4 text-zinc-400" />
                          Export Chat History
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleClearWorkspaceChat();
                            setActiveNavMenu(null);
                          }}
                          className="w-full text-left px-3.5 py-2.5 hover:bg-[#27272a] text-red-400 hover:text-red-300 flex items-center gap-2 font-medium border-t border-[#27272a]/40 mt-1"
                        >
                          <Trash2 className="w-4 h-4" />
                          Clear Chat Room
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Database Dropdown Trigger */}
              <div className="relative" onClick={(e) => e.stopPropagation()}>
                <span 
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveNavMenu(activeNavMenu === "database" ? null : "database");
                  }}
                  className={`hover:text-white cursor-pointer transition py-1 px-2.5 rounded font-bold text-sm tracking-wide ${
                    activeNavMenu === "database" ? "text-white bg-[#27272a]" : ""
                  }`}
                >
                  Database
                </span>
                {activeNavMenu === "database" && (
                  <div className="absolute left-0 mt-2.5 w-60 bg-[#121214] border border-[#27272a] rounded-lg shadow-xl py-1 z-50 text-xs text-[#e4e4e7]" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (selectedSessionId) {
                          setShowSqlModal(true);
                        } else {
                          alert("Please open a workspace first!");
                        }
                        setActiveNavMenu(null);
                      }}
                      className="w-full text-left px-3.5 py-2.5 hover:bg-[#27272a] hover:text-white flex items-center gap-2 font-medium"
                    >
                      <Database className="w-4 h-4 text-zinc-400" />
                      Connect SQL Database...
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        alert("DuckDB memory sandbox database is active for raw data analysis queries.");
                        setActiveNavMenu(null);
                      }}
                      className="w-full text-left px-3.5 py-2.5 hover:bg-[#27272a] hover:text-white flex items-center gap-2 font-medium"
                    >
                      <Terminal className="w-4 h-4 text-zinc-400" />
                      DuckDB Sandbox Info
                    </button>
                  </div>
                )}
              </div>

              {/* Help Trigger */}
              <div className="relative" onClick={(e) => e.stopPropagation()}>
                <span 
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowHelpModal(true);
                    setActiveNavMenu(null);
                  }}
                  className="hover:text-white cursor-pointer transition py-1 px-2.5 rounded font-bold text-sm tracking-wide"
                >
                  Help
                </span>
              </div>
            </div>
          </div>
        </div>
        
        {/* Connection status on top right */}
        <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
          <button 
            onClick={(e) => {
              e.stopPropagation();
              setSelectedSessionId(null);
            }}
            className="px-3.5 py-1.5 bg-[#1c1c1f] hover:bg-[#27272a] border border-[#27272a] rounded-lg text-xs text-zinc-300 hover:text-white font-semibold transition"
          >
            Open Workspace
          </button>
          <div className="flex items-center gap-1.5 text-xs bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-lg text-zinc-400 font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            Connected
          </div>
        </div>
      </div>

      {/* 2. MAIN WORKSPACE CONTAINER */}
      <div className="flex flex-1 overflow-hidden relative">
        
        {/* Blurred/Active Dashboard layout */}
        <div className={`flex flex-1 overflow-hidden transition-all duration-300 ${
          !selectedSessionId ? "filter blur-[1.5px] pointer-events-none opacity-40" : ""
        }`}>
          
          {/* LEFT SIDEBAR - SESSIONS NAVIGATION */}
          <div className="w-64 border-r border-[#27272a] bg-[#121214] flex flex-col shrink-0">
            <div className="p-4 border-b border-[#27272a] flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-white animate-pulse" />
              <span className="font-semibold text-sm bg-gradient-to-r from-white via-zinc-200 to-zinc-400 bg-clip-text text-transparent">
                Workspaces
              </span>
            </div>
            
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => {
                    if (editingSessionId !== s.id) {
                      setSelectedSessionId(s.id);
                    }
                  }}
                  className={`flex items-center justify-between p-2.5 rounded-lg text-sm cursor-pointer group transition-all duration-200 relative ${
                    selectedSessionId === s.id 
                      ? "bg-white text-black font-semibold shadow-md border border-white" 
                      : "hover:bg-[#1c1c1f] text-zinc-400 border border-transparent"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate flex-1 pr-1">
                    <MessageSquare className={`w-4 h-4 shrink-0 ${selectedSessionId === s.id ? "text-black" : "text-zinc-550"}`} />
                    {editingSessionId === s.id ? (
                      <input
                        type="text"
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && editingTitle.trim()) {
                            handleRenameSession(s.id, editingTitle);
                            setEditingSessionId(null);
                          } else if (e.key === "Escape") {
                            setEditingSessionId(null);
                          }
                        }}
                        className={`border rounded px-1.5 py-0.5 text-xs focus:outline-none w-full ${
                          selectedSessionId === s.id ? "bg-zinc-100 border-zinc-300 text-black" : "bg-black border-zinc-800 text-white"
                        }`}
                        autoFocus
                      />
                    ) : (
                      <span className="truncate">{s.title}</span>
                    )}
                  </div>
                  
                  {editingSessionId !== s.id && (
                    <div className="relative shrink-0" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => setSessionMenuId(sessionMenuId === s.id ? null : s.id)}
                        className={`opacity-0 group-hover:opacity-100 p-1 rounded transition duration-200 ${
                          selectedSessionId === s.id ? "text-black hover:bg-zinc-200" : "text-zinc-400 hover:bg-zinc-800 hover:text-white"
                        }`}
                      >
                        <MoreVertical className="w-3.5 h-3.5" />
                      </button>
                      {sessionMenuId === s.id && (
                        <div className="absolute right-0 mt-1 w-36 bg-[#121214] border border-[#27272a] rounded-lg shadow-xl py-1 z-50 text-xs text-[#e4e4e7]">
                          <button
                            onClick={() => {
                              setEditingSessionId(s.id);
                              setEditingTitle(s.title);
                              setSessionMenuId(null);
                            }}
                            className="w-full text-left px-3 py-1.5 hover:bg-[#27272a] hover:text-white flex items-center gap-1.5"
                          >
                            <Edit3 className="w-3 h-3" />
                            Rename
                          </button>
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(s.id);
                              setCopiedSessionId(s.id);
                              setTimeout(() => setCopiedSessionId(null), 1500);
                            }}
                            className="w-full text-left px-3 py-1.5 hover:bg-[#27272a] hover:text-white flex items-center gap-1.5"
                          >
                            <FileText className="w-3 h-3" />
                            {copiedSessionId === s.id ? "Copied!" : "Copy ID"}
                          </button>
                          <button
                            onClick={(e) => {
                              handleDeleteSession(s.id, e);
                              setSessionMenuId(null);
                            }}
                            className="w-full text-left px-3 py-1.5 hover:bg-[#27272a] text-red-400 hover:text-red-300 flex items-center gap-1.5 border-t border-[#27272a] mt-1"
                          >
                            <Trash2 className="w-3 h-3" />
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {sessions.length === 0 && (
                <div className="text-center text-xs text-zinc-500 mt-8">
                  No sessions created yet.
                </div>
              )}
            </div>
          </div>

          {/* THE 30-40-30 PANELS */}
          <div className="flex flex-1 overflow-hidden">
            
            {/* PANE 1: LEFT WORKSPACE/PROFILER (30%) */}
            <div 
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`w-[30%] border-r border-[#27272a] bg-[#121214] flex flex-col overflow-hidden relative ${
                isDragging ? "border-dashed border-white bg-zinc-900/60" : ""
              }`}
            >
              {/* Hidden file input */}
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileUpload} 
                className="hidden" 
                accept=".csv,.json,.xls,.xlsx" 
              />

              {/* Progress Bar / Loader overlay */}
              {isUploading && (
                <div className="absolute inset-0 bg-black/80 z-50 flex flex-col items-center justify-center p-4 text-center">
                  <Loader2 className="w-8 h-8 animate-spin text-white mb-2" />
                  <span className="text-sm font-semibold text-white">Uploading Dataset...</span>
                  {uploadProgress !== null && (
                    <div className="w-48 bg-zinc-800 rounded-full h-1.5 mt-3 overflow-hidden border border-zinc-700">
                      <div 
                        className="bg-white h-1.5 rounded-full transition-all duration-300" 
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="p-4 border-b border-[#27272a] flex items-center justify-between">
                <div className="flex items-center gap-2 max-w-[70%]">
                  <Database className="w-5 h-5 text-white shrink-0" />
                  {isEditingWorkspaceTitle && selectedSessionId ? (
                    <input
                      type="text"
                      value={tempWorkspaceTitle}
                      onChange={(e) => setTempWorkspaceTitle(e.target.value)}
                      onBlur={() => {
                        if (tempWorkspaceTitle.trim() && tempWorkspaceTitle !== sessions.find(s => s.id === selectedSessionId)?.title) {
                          handleRenameSession(selectedSessionId, tempWorkspaceTitle);
                        }
                        setIsEditingWorkspaceTitle(false);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          if (tempWorkspaceTitle.trim() && tempWorkspaceTitle !== sessions.find(s => s.id === selectedSessionId)?.title) {
                            handleRenameSession(selectedSessionId, tempWorkspaceTitle);
                          }
                          setIsEditingWorkspaceTitle(false);
                        } else if (e.key === "Escape") {
                          setIsEditingWorkspaceTitle(false);
                        }
                      }}
                      className="bg-black border border-zinc-700 rounded px-1.5 py-0.5 text-xs text-white focus:outline-none focus:border-white"
                      autoFocus
                    />
                  ) : (
                    <div className="flex items-center gap-1.5 truncate group/title cursor-pointer" onClick={() => {
                      if (selectedSessionId) {
                        setTempWorkspaceTitle(sessions.find(s => s.id === selectedSessionId)?.title || "");
                        setIsEditingWorkspaceTitle(true);
                      }
                    }}>
                      <h2 className="font-semibold text-white truncate">
                        {selectedSessionId ? (sessions.find(s => s.id === selectedSessionId)?.title || "Workspace Profile") : "Welcome Workspace"}
                      </h2>
                      {selectedSessionId && (
                        <Edit3 className="w-3.5 h-3.5 text-zinc-500 opacity-0 group-hover/title:opacity-100 transition-opacity" />
                      )}
                    </div>
                  )}
                </div>
                {dataset && (
                  <button
                    onClick={() => setShowDeleteConfirmModal(true)}
                    className="text-[10px] font-bold uppercase tracking-wider text-red-400 hover:text-red-350 hover:bg-red-950/20 px-2.5 py-1 bg-[#1c1c1f] border border-[#27272a] hover:border-red-900 rounded-md transition shrink-0"
                  >
                    Delete Source
                  </button>
                )}
              </div>

              <div className="flex-1 overflow-y-auto p-4 flex flex-col">
                {dataset && dataset.schema_json ? (
                  <div className="space-y-5">
                    <div 
                      onClick={() => window.open(`${API_BASE}/sessions/${selectedSessionId}/dataset/view`, '_blank')}
                      className="flex items-center justify-between gap-2 mb-4 bg-[#1c1c1f] p-3 rounded-lg border border-[#27272a] hover:border-zinc-500 hover:bg-[#202024] relative group cursor-pointer transition-all duration-300"
                      title="Open dataset in new tab"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="w-5 h-5 text-zinc-300 shrink-0" />
                        <div className="min-w-0">
                          <div className="text-white text-sm font-medium truncate max-w-[150px]">
                            {dataset.file_name}
                          </div>
                          <div className="text-xs text-zinc-400">
                            {dataset.schema_json.total_rows?.toLocaleString() || "0"} total rows loaded
                          </div>
                        </div>
                      </div>
                      
                      <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex items-center gap-1 bg-zinc-800 border border-zinc-700 px-2 py-1 rounded text-[9px] text-zinc-300 font-semibold uppercase tracking-wider shrink-0">
                        <span>Open</span>
                        <ChevronRight className="w-3 h-3" />
                      </div>
                    </div>

                    <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-300 mb-3">
                      Ingested Data Schema
                    </h3>
                    <div className="space-y-2.5">
                      {(dataset.schema_json.columns || []).map((col) => {
                        const dtype = dataset.schema_json.dtypes?.[col] || "Unknown";
                        const nullRate = dataset.schema_json.null_rates?.[col] || "0.00%";
                        const anomaly = dataset.schema_json.anomalies?.[col];
                        const hasAnomaly = anomaly && anomaly !== "No significant statistical anomalies detected." && anomaly !== "N/A (Non-numeric field)";
                        const stats = dataset.schema_json.numerical_stats?.[col];
                        
                        const isNum = ["int", "float", "double", "num", "decimal"].some(t => dtype.toLowerCase().includes(t));
                        const isDate = ["date", "time", "timestamp"].some(t => dtype.toLowerCase().includes(t));

                        return (
                          <div 
                            key={col} 
                            onClick={() => setSelectedStatsCol(selectedStatsCol === col ? null : col)}
                            onMouseEnter={() => setHoveredColumnAnomaly(col)}
                            onMouseLeave={() => setHoveredColumnAnomaly(null)}
                            className={`p-3.5 rounded-xl border transition-all duration-300 cursor-pointer relative flex flex-col group ${
                              selectedStatsCol === col 
                                ? "bg-[#1d1d22] border-amber-500 shadow-md shadow-amber-500/5" 
                                : "bg-[#18181b]/60 border-[#27272a] hover:bg-[#1c1c20] hover:border-zinc-700"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="shrink-0 opacity-90">
                                  {isNum ? (
                                    <span className="text-[9px] bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 px-1.5 py-0.5 rounded font-mono font-bold">NUM</span>
                                  ) : isDate ? (
                                    <span className="text-[9px] bg-blue-950/60 text-blue-400 border border-blue-800/40 px-1.5 py-0.5 rounded font-mono font-bold">DATE</span>
                                  ) : (
                                    <span className="text-[9px] bg-amber-950/60 text-amber-400 border border-amber-800/40 px-1.5 py-0.5 rounded font-mono font-bold">TXT</span>
                                  )}
                                </span>
                                <span className="text-sm font-semibold text-zinc-150 truncate" title={col}>
                                  {col}
                                </span>
                                {hasAnomaly && (
                                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 animate-pulse shrink-0" />
                                )}
                              </div>
                              <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wide shrink-0">
                                {dtype}
                              </span>
                            </div>

                            {/* Collateral Equal-spaced Grid for Descriptive Statistics + Null Rate */}
                            {selectedStatsCol === col && (
                              <div className="mt-3.5 pt-3 border-t border-[#27272a]/60 space-y-3 animate-fade-in select-text">
                                <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                                  <div className="bg-black/35 border border-[#27272a]/70 rounded-lg p-2.5 flex flex-col">
                                    <span className="text-[9px] uppercase tracking-wider text-zinc-500">Null Rate</span>
                                    <span className="font-semibold text-zinc-300 mt-1 text-xs">{nullRate}</span>
                                  </div>
                                  {stats && (
                                    <>
                                      <div className="bg-black/35 border border-[#27272a]/70 rounded-lg p-2.5 flex flex-col">
                                        <span className="text-[9px] uppercase tracking-wider text-zinc-500">Mean Value</span>
                                        <span className="font-semibold text-zinc-300 mt-1 text-xs">{stats.mean}</span>
                                      </div>
                                      <div className="bg-black/35 border border-[#27272a]/70 rounded-lg p-2.5 flex flex-col">
                                        <span className="text-[9px] uppercase tracking-wider text-zinc-500">Median</span>
                                        <span className="font-semibold text-zinc-300 mt-1 text-xs">{stats.median}</span>
                                      </div>
                                      <div className="bg-black/35 border border-[#27272a]/70 rounded-lg p-2.5 flex flex-col">
                                        <span className="text-[9px] uppercase tracking-wider text-zinc-500">Std Dev</span>
                                        <span className="font-semibold text-zinc-300 mt-1 text-xs">{stats.std}</span>
                                      </div>
                                      <div className="bg-black/35 border border-[#27272a]/70 rounded-lg p-2.5 flex flex-col">
                                        <span className="text-[9px] uppercase tracking-wider text-zinc-500">Min</span>
                                        <span className="font-semibold text-zinc-300 mt-1 text-xs">{stats.min}</span>
                                      </div>
                                      <div className="bg-black/35 border border-[#27272a]/70 rounded-lg p-2.5 flex flex-col">
                                        <span className="text-[9px] uppercase tracking-wider text-zinc-500">Max</span>
                                        <span className="font-semibold text-zinc-300 mt-1 text-xs">{stats.max}</span>
                                      </div>
                                    </>
                                  )}
                                </div>

                                {hasAnomaly && (
                                  <div className="flex items-start gap-2 p-2.5 bg-yellow-950/30 border border-yellow-800/40 rounded-lg text-[11px] text-yellow-300">
                                    <AlertTriangle className="w-4 h-4 shrink-0 text-yellow-400 mt-0.5" />
                                    <span className="leading-normal">{anomaly}</span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col space-y-4">
                    <div className="flex-1 flex flex-col items-center justify-center text-center p-4 border-2 border-dashed border-zinc-700 hover:border-zinc-500 rounded-2xl bg-[#1c1c1f]/40 transition-all duration-300">
                      <Upload className="w-6 h-6 text-zinc-400 mb-2" />
                      <h4 className="text-white font-semibold text-sm mb-1">Import Dataset</h4>
                      <p className="text-[10px] text-zinc-400 max-w-[180px] mb-3 leading-relaxed">CSV, JSON, or Excel</p>
                      <button 
                        onClick={() => fileInputRef.current?.click()}
                        className="px-4 py-1.5 bg-white text-black text-xs font-bold rounded-lg hover:bg-zinc-200"
                      >
                        Browse Files
                      </button>
                    </div>
                    <div className="flex-1 flex flex-col items-center justify-center text-center p-4 border border-[#27272a] bg-[#1c1c1f]/20 rounded-2xl">
                      <Database className="w-6 h-6 text-zinc-400 mb-2" />
                      <h4 className="text-white font-semibold text-sm mb-1">Connect SQL</h4>
                      <p className="text-[10px] text-zinc-400 max-w-[180px] mb-3">PostgreSQL or MySQL</p>
                      <button 
                        onClick={() => setShowSqlModal(true)}
                        className="px-4 py-1.5 bg-[#1c1c1f] border border-[#3f3f46] text-zinc-200 text-xs font-bold rounded-lg hover:bg-[#27272a] hover:text-white transition"
                      >
                        Connect
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
            
            {/* PANE 2: MIDDLE CONVERSATIONAL CHAT (Resizes dynamically) */}
            <div className="flex-1 min-w-[30%] border-r border-[#27272a] bg-[#09090b] flex flex-col overflow-hidden">
              <div className="p-4 border-b border-[#27272a] bg-[#121214] flex items-center justify-between">
                <h2 className="font-semibold text-white">Analysis Room</h2>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* Default welcome guide chat background when no session is selected */}
                {!selectedSessionId || messages.length === 0 ? (
                  <div className="space-y-4">
                    <div className="bg-[#1c1c1f] border border-[#27272a] rounded-2xl p-4 text-sm text-zinc-300 space-y-2">
                      <h3 className="font-bold text-white text-base">Welcome to the Autonomous Data Agent</h3>
                      <p className="text-xs text-zinc-400 leading-relaxed">
                        This is an interactive analytics environment. Once you launch a workspace, you can ingest files, query stats, and automatically visualize datasets.
                      </p>
                    </div>
                    <div className="bg-[#1c1c1f] border border-[#27272a] rounded-2xl p-4 text-sm text-zinc-300 space-y-2">
                      <h4 className="font-bold text-white text-xs uppercase tracking-wider text-zinc-400">Quick Guide:</h4>
                      <ol className="list-decimal pl-4 space-y-1.5 text-xs text-zinc-400">
                        <li>Import your dataset (CSV, JSON, or Excel) or connect to your database.</li>
                        <li>Ask query calculations directly in natural language (e.g., "Find the average salary by department").</li>
                        <li>Visualize graphs dynamically in the Visual Analytics viewport.</li>
                      </ol>
                    </div>
                  </div>
                ) : (
                  messages.map((m, idx) => (
                    <div key={m.id || `msg-${idx}`} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
                      <div className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                        m.role === "user" ? "bg-white text-black rounded-br-none font-medium shadow-md" : "bg-[#1c1c1f] border border-[#27272a] text-zinc-200 rounded-bl-none"
                      }`}>
                        <div className="whitespace-pre-wrap break-words">{renderMessageContent(m.content)}</div>
                        {m.generated_code && (
                          <div className="mt-2.5 pt-2 border-t border-[#27272a]">
                            <button
                              onClick={() => toggleCode(m.id)}
                              className="text-xs text-zinc-400 hover:text-white flex items-center gap-1 font-mono"
                            >
                              <Terminal className="w-3.5 h-3.5" />
                              {showCodeMap[m.id] ? "Hide Generated Code" : "Show Generated Code"}
                            </button>
                            {showCodeMap[m.id] && (
                              <pre className="mt-2 p-2.5 bg-black rounded border border-[#27272a] text-xs font-mono overflow-x-auto text-emerald-400 max-w-full">
                                <code>{m.generated_code}</code>
                              </pre>
                            )}
                          </div>
                        )}
                      </div>
                      
                      {/* Follow-up questions render beneath the message bubble */}
                      {m.role === "assistant" && streamingMsgId !== m.id && m.follow_ups && m.follow_ups.length > 0 && (
                        <div className="mt-2 flex flex-col items-start pl-3">
                          <div className="flex flex-wrap gap-2">
                            {m.follow_ups.map((fq, fidx) => (
                              <button
                                key={`fq-${fidx}`}
                                onClick={() => executeAnalysisQuestion(fq)}
                                disabled={isQuerying}
                                className="text-xs text-zinc-300 hover:text-white bg-[#1c1c1f] hover:bg-[#27272a] border border-[#27272a] rounded-lg px-3 py-1.5 transition text-left cursor-pointer disabled:opacity-50 disabled:pointer-events-none"
                              >
                                💡 {fq}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
                {isQuerying && !streamingMsgId && (
                  <div className="flex flex-col items-start animate-fade-in">
                    <div className="bg-[#1c1c1f] border border-[#27272a] text-zinc-400 rounded-2xl rounded-bl-none px-4 py-3 text-sm flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              <form onSubmit={handleAskQuestion} className="p-4 pb-7 border-t border-[#27272a] bg-[#121214]">
                {selectedDiagram && (
                  <div className="mb-2 flex items-center justify-between bg-[#1c1c1f] border border-[#27272a] rounded-lg px-3 py-1.5 text-[11px] text-zinc-300">
                    <div className="flex items-center gap-1.5 truncate pr-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse shrink-0" />
                      <span className="truncate">Replying to: <strong className="text-white font-medium">"{selectedDiagram.summary || selectedDiagram.question}"</strong></span>
                    </div>
                    <button 
                      type="button" 
                      onClick={() => setSelectedDiagram(null)}
                      className="text-zinc-400 hover:text-white transition font-mono shrink-0 uppercase tracking-wider text-[9px] font-bold"
                    >
                      [Clear]
                    </button>
                  </div>
                )}
                <div className="flex gap-2">
                  <input
                    type="text"
                    ref={questionInputRef}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    disabled={!selectedSessionId || isQuerying}
                    placeholder={selectedSessionId ? "Ask a question about the dataset..." : "Select or open a workspace session to query..."}
                    className="flex-1 bg-black border border-[#27272a] rounded-lg px-3 py-2.5 text-sm focus:outline-none text-white placeholder-zinc-600 disabled:opacity-60"
                  />
                  {(isQuerying || streamingMsgId) ? (
                    <button 
                      type="button" 
                      onClick={stopStreaming}
                      className="bg-red-950/80 hover:bg-red-900 border border-red-800 text-red-200 px-4 py-2.5 rounded-lg text-sm font-semibold transition flex items-center justify-center gap-1.5"
                    >
                      <span className="w-2.5 h-2.5 bg-red-400 rounded-sm" />
                      <span>Stop</span>
                    </button>
                  ) : (
                    <button 
                      type="submit"
                      disabled={!selectedSessionId || !question.trim()}
                      className="bg-white hover:bg-zinc-200 disabled:bg-zinc-800 disabled:text-zinc-500 text-black px-4 py-2.5 rounded-lg text-sm font-semibold transition flex items-center justify-center gap-1.5"
                    >
                      <Send className="w-4 h-4" />
                      <span>Analyze</span>
                    </button>
                  )}
                </div>
              </form>
              {/* Anomalies Bottom Drawer */}
              {hoveredColumnAnomaly && dataset && dataset.schema_json && (
                (() => {
                  const col = hoveredColumnAnomaly;
                  const anomaly = dataset.schema_json.anomalies?.[col] || "No statistical anomalies detected.";
                  
                  return (
                    <div 
                      className="absolute bottom-0 left-0 right-0 h-[140px] bg-[#1a1410]/95 backdrop-blur-md border-t border-amber-600/50 shadow-2xl z-40 transition-all duration-300 transform translate-y-0 flex flex-col p-4 animate-slide-up"
                    >
                      <div className="flex items-start gap-2.5">
                        <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5 animate-pulse" />
                        <div className="space-y-1">
                          <div className="text-xs font-bold text-amber-400 uppercase tracking-wider font-mono">
                            Anomaly Status &mdash; Column "{col}"
                          </div>
                          <p className="text-sm text-amber-200/90 leading-relaxed font-sans">
                            {anomaly}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })()
              )}
            </div>

            {/* PANE 3: RIGHT VISUALS PERSISTENT VIEWPORT */}
            <div 
              className={`transition-all duration-300 ease-in-out flex flex-col overflow-hidden shrink-0 border-l border-[#27272a] ${
                isVisualsOpen ? "w-[30%] min-w-[280px] bg-[#09090b]" : "w-12 bg-[#121214] hover:bg-[#1c1c1f] cursor-pointer"
              }`}
              onClick={() => {
                if (!isVisualsOpen) {
                  setIsVisualsOpen(true);
                }
              }}
            >
              {!isVisualsOpen ? (
                <div className="flex-1 flex flex-col items-center justify-between py-6 h-full select-none">
                  {/* Chevron pointing left to expand */}
                  <ChevronRight className="w-5 h-5 text-zinc-455 rotate-180" />
                  
                  {/* Vertical title written vertically */}
                  <div className="flex-1 flex items-center justify-center">
                    <span 
                      style={{ writingMode: "vertical-rl" }} 
                      className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[#a1a1aa] select-none transform rotate-180 flex items-center gap-2"
                    >
                      <TrendingUp className="w-3.5 h-3.5 inline-block transform -rotate-90 text-zinc-400" />
                      Visual Analytics
                    </span>
                  </div>

                  {/* Badging showing plot count */}
                  {messages.filter(m => m.chart_url).length > 0 ? (
                    <span className="text-[9px] font-bold font-mono bg-zinc-800 border border-zinc-700 text-zinc-350 px-2 py-0.5 rounded-full">
                      {messages.filter(m => m.chart_url).length}
                    </span>
                  ) : (
                    <div className="h-4 w-4 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#3f3f46]" />
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <div className="p-4 border-b border-[#27272a] bg-[#121214] flex items-center justify-between shrink-0">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-white" />
                      <h2 className="font-semibold text-white">Visual Analytics</h2>
                    </div>
                    <div className="flex items-center gap-2">
                      {messages.filter(m => m.chart_url).length > 0 && (
                        <span className="text-[10px] font-mono bg-zinc-900 border border-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full">
                          {messages.filter(m => m.chart_url).length} plots
                        </span>
                      )}
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setIsVisualsOpen(false);
                        }}
                        className="p-1 hover:bg-[#27272a] rounded text-zinc-400 hover:text-white transition"
                        title="Collapse Panel"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {messages.filter(m => m.chart_url).length > 0 ? (
                      messages.filter(m => m.chart_url).map((m, cidx) => {
                        const chartUrl = m.chart_url || "";
                        const fullUrl = chartUrl.startsWith("http") ? chartUrl : `http://localhost:8000${chartUrl}`;
                        const msgIdx = messages.findIndex(msg => msg.id === m.id);
                        const associatedQuestion = msgIdx > 0 ? messages[msgIdx - 1].content : "Data query visualization";
                        
                        const plotTitle = m.chart_summary ? m.chart_summary.split('.')[0] : associatedQuestion;
                        const plotTime = new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                        const isCodeOpen = !!showChartCodeMap[m.id];

                        return (
                          <div 
                            key={m.id || `chart-${cidx}`}
                            className="group relative bg-[#1c1c1f] border border-[#27272a] hover:border-zinc-500 rounded-xl overflow-hidden transition-all duration-300 flex flex-col"
                          >
                            {/* Header: Title of the plot and a timestamp */}
                            <div className="px-3.5 py-2.5 border-b border-[#27272a]/60 bg-black/40 flex items-start justify-between gap-2 shrink-0">
                              <div className="flex flex-col min-w-0 flex-1">
                                <span className="text-xs font-bold text-white truncate" title={plotTitle}>
                                  {plotTitle}
                                </span>
                                <span className="text-[10px] text-zinc-400 mt-0.5 font-mono">Plot #{cidx + 1}</span>
                              </div>
                              <span className="text-[10px] text-zinc-550 font-mono shrink-0 mt-0.5">
                                {plotTime}
                              </span>
                            </div>

                            {/* Image body */}
                            <div 
                              onClick={() => setZoomedChartUrl(fullUrl)}
                              className="flex-1 min-h-[160px] p-3 flex items-center justify-center bg-[#09090b]/45 cursor-zoom-in group-hover:opacity-90 transition-opacity relative border-b border-[#27272a]/40"
                            >
                              <img 
                                src={fullUrl} 
                                alt={plotTitle} 
                                className="max-h-[180px] object-contain rounded border border-transparent shadow-md"
                              />
                            </div>

                            {/* Collapsible Inline Code viewer */}
                            {isCodeOpen && m.generated_code && (
                              <div className="bg-black/90 p-3 font-mono text-[10px] text-emerald-400 border-b border-[#27272a] max-h-[150px] overflow-y-auto select-text">
                                <span className="text-[9px] uppercase tracking-wider text-zinc-500 font-mono block mb-1">Generated Python Code</span>
                                <pre className="whitespace-pre overflow-x-auto">
                                  <code>{m.generated_code}</code>
                                </pre>
                              </div>
                            )}

                            {/* Footer (The Action Strip) */}
                            <div className="px-2.5 py-2 bg-[#121214] flex items-center justify-between gap-2 shrink-0">
                              <button
                                onClick={() => setShowChartCodeMap(prev => ({ ...prev, [m.id]: !prev[m.id] }))}
                                className={`flex-1 py-1.5 rounded-lg border text-[11px] font-semibold flex items-center justify-center gap-1 transition ${
                                  isCodeOpen 
                                    ? "bg-white text-black border-white" 
                                    : "bg-[#1c1c1f] text-zinc-300 border-[#27272a] hover:bg-[#27272a] hover:text-white"
                                }`}
                              >
                                <Code className="w-3.5 h-3.5" />
                                <span>Code</span>
                              </button>
                              
                              <button
                                onClick={() => {
                                  setSelectedDiagram({
                                    id: m.id,
                                    chartUrl: fullUrl,
                                    code: m.generated_code || "",
                                    summary: m.chart_summary || "Visual chart",
                                    question: associatedQuestion
                                  });
                                  setQuestion("");
                                  setTimeout(() => {
                                    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
                                    questionInputRef.current?.focus();
                                  }, 100);
                                }}
                                className="flex-1 py-1.5 rounded-lg bg-[#1c1c1f] text-zinc-300 border border-[#27272a] hover:bg-[#27272a] hover:text-white text-[11px] font-semibold flex items-center justify-center gap-1 transition"
                              >
                                <MessageSquare className="w-3.5 h-3.5" />
                                <span>Discuss</span>
                              </button>
                              
                              <button
                                onClick={() => {
                                  const link = document.createElement("a");
                                  link.href = fullUrl;
                                  link.download = `plot_${cidx + 1}.png`;
                                  document.body.appendChild(link);
                                  link.click();
                                  document.body.removeChild(link);
                                }}
                                className="flex-1 py-1.5 rounded-lg bg-[#1c1c1f] text-zinc-300 border border-[#27272a] hover:bg-[#27272a] hover:text-white text-[11px] font-semibold flex items-center justify-center gap-1 transition"
                              >
                                <Download className="w-3.5 h-3.5" />
                                <span>Save</span>
                              </button>
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="h-64 flex flex-col items-center justify-center text-center">
                        <div className="w-12 h-12 rounded-full bg-[#1c1c1f] border border-[#27272a] flex items-center justify-center text-zinc-500 mb-3">
                          <ImageIcon className="w-6 h-6" />
                        </div>
                        <h3 className="text-white font-medium mb-1">No Visualizations</h3>
                        <p className="text-[10px] text-zinc-550 max-w-[180px]">Plot generation requires numerical values queries.</p>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>

          </div>
        </div>

        {/* 3. OPEN WORKSPACE DIALOG MODAL (Colab style) */}
        {!selectedSessionId && (
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 md:p-8">
            <div className="bg-[#121214] border border-[#27272a] rounded-xl shadow-2xl max-w-4xl w-full h-[550px] flex flex-col overflow-hidden text-[#e4e4e7] animate-fade-in">
              
              {/* Header */}
              <div className="px-6 py-4 border-b border-[#27272a] flex items-center justify-between bg-[#121214]">
                <h2 className="text-lg font-semibold text-white">Open workspace</h2>
              </div>
              
              {/* Content Body */}
              <div className="flex-1 flex overflow-hidden">
                <div className="flex-1 bg-[#09090b] flex flex-col overflow-hidden p-6">
                  {/* Search bar */}
                  <div className="flex items-center gap-2.5 mb-6 bg-[#1c1c1f] border border-[#27272a] rounded-lg px-4 py-2.5">
                    <span className="text-zinc-400 text-sm">🔎</span>
                    <input 
                      type="text"
                      placeholder="Search workspaces"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="flex-1 bg-transparent text-sm text-white focus:outline-none placeholder-zinc-500"
                    />
                  </div>
                  
                  {/* Table Headers */}
                  <div className="grid grid-cols-12 text-[10px] font-mono uppercase tracking-wider text-zinc-400 pb-2 border-b border-[#27272a] px-3">
                    <div className="col-span-8">Title</div>
                    <div className="col-span-3">Created</div>
                    <div className="col-span-1 text-right">Actions</div>
                  </div>
                  
                  {/* Table Body */}
                  <div className="flex-1 overflow-y-auto py-2 space-y-0.5 divide-y divide-[#1c1c1f]">
                    {filteredSessions.map((s) => {
                      const isEditing = editingSessionId === s.id;
                      return (
                        <div 
                          key={s.id}
                          onClick={() => {
                            if (!isEditing) {
                              setSelectedSessionId(s.id);
                            }
                          }}
                          className="grid grid-cols-12 items-center text-sm py-3.5 px-3 hover:bg-[#1c1c1f] rounded-lg transition duration-150 cursor-pointer group"
                        >
                          <div className="col-span-8 flex items-center gap-3 pr-4">
                            <Database className="w-4 h-4 text-zinc-400 shrink-0" />
                            {isEditing ? (
                              <input
                                type="text"
                                value={editingTitle}
                                onChange={(e) => setEditingTitle(e.target.value)}
                                onClick={(e) => e.stopPropagation()}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" && editingTitle.trim()) {
                                    handleRenameSession(s.id, editingTitle);
                                    setEditingSessionId(null);
                                  } else if (e.key === "Escape") {
                                    setEditingSessionId(null);
                                  }
                                }}
                                className="bg-[#1c1c1f] border border-zinc-500 rounded px-2 py-0.5 text-sm text-white focus:outline-none w-full"
                                autoFocus
                              />
                            ) : (
                              <span className="truncate font-medium text-zinc-200 group-hover:text-white group-hover:underline">
                                {s.title}
                              </span>
                            )}
                          </div>
                          
                          <div className="col-span-3 text-xs text-zinc-400">
                            {new Date(s.created_at).toLocaleDateString(undefined, {
                              month: 'short',
                              day: 'numeric',
                              year: 'numeric'
                            })}
                          </div>
                          
                          <div className="col-span-1 flex items-center justify-end gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150" onClick={e => e.stopPropagation()}>
                            {isEditing ? (
                              <>
                                <button
                                  onClick={() => {
                                    if (editingTitle.trim()) {
                                      handleRenameSession(s.id, editingTitle);
                                      setEditingSessionId(null);
                                    }
                                  }}
                                  className="p-1 hover:bg-[#27272a] rounded text-emerald-400"
                                >
                                  <Check className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => setEditingSessionId(null)}
                                  className="p-1 hover:bg-[#27272a] rounded text-red-400"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  onClick={() => {
                                    setEditingSessionId(s.id);
                                    setEditingTitle(s.title);
                                  }}
                                  className="p-1 hover:bg-[#27272a] rounded text-zinc-400 hover:text-white"
                                  title="Rename"
                                >
                                  <Edit3 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={(e) => handleDeleteSession(s.id, e)}
                                  className="p-1 hover:bg-[#27272a] rounded text-zinc-400 hover:text-red-400"
                                  title="Delete"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      );
                    })}
                    {filteredSessions.length === 0 && (
                      <div className="text-center text-xs text-zinc-555 py-16">
                        No workspaces found.
                      </div>
                    )}
                  </div>
                </div>
              </div>
              
              {/* Modal Bottom Bar */}
              <div className="px-6 py-4 border-t border-[#27272a] bg-[#121214] flex items-center justify-between">
                <button
                  onClick={() => {
                    setNewSessionTitle("");
                    setShowCreateInput(true);
                  }}
                  className="px-5 py-2.5 bg-white hover:bg-zinc-200 text-black text-sm font-semibold rounded-full transition flex items-center gap-2"
                >
                  <Plus className="w-4 h-4 stroke-[3px]" />
                  New workspace
                </button>
                
                <button
                  onClick={() => {
                    if (sessions.length > 0) {
                      setSelectedSessionId(sessions[0].id);
                    }
                  }}
                  className="text-sm font-semibold text-zinc-400 hover:text-white px-3 py-2 transition"
                >
                  Cancel
                </button>
              </div>

            </div>
          </div>
        )}

      </div>

      {/* SQL Connection Form Modal */}
      {showSqlModal && (
        <div className="fixed inset-0 bg-black/85 z-[100] flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-[#121214] border border-[#27272a] rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#27272a]">
              <div className="flex items-center gap-2">
                <Database className="w-5 h-5 text-white" />
                <h3 className="text-lg font-bold text-white">Connect SQL Database</h3>
              </div>
              <button 
                onClick={() => setShowSqlModal(false)}
                className="text-zinc-400 hover:text-white p-1 rounded hover:bg-[#1c1c1f]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSqlConnect} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1">Database Type</label>
                  <select
                    value={dbType}
                    onChange={(e) => {
                      setDbType(e.target.value);
                      setDbPort(e.target.value === "mysql" ? "3306" : "5432");
                    }}
                    className="w-full bg-black border border-[#27272a] rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-500"
                  >
                    <option value="postgresql">PostgreSQL</option>
                    <option value="mysql">MySQL</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1">Host</label>
                  <input
                    type="text"
                    required
                    placeholder="localhost"
                    value={dbHost}
                    onChange={(e) => setDbHost(e.target.value)}
                    className="w-full bg-black border border-[#27272a] rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1">Port</label>
                  <input
                    type="text"
                    required
                    placeholder={dbType === "mysql" ? "3306" : "5432"}
                    value={dbPort}
                    onChange={(e) => setDbPort(e.target.value)}
                    className="w-full bg-black border border-[#27272a] rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1">Database Name</label>
                  <input
                    type="text"
                    required
                    placeholder="my_database"
                    value={dbName}
                    onChange={(e) => setDbName(e.target.value)}
                    className="w-full bg-black border border-[#27272a] rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1">Username</label>
                  <input
                    type="text"
                    required
                    placeholder="postgres"
                    value={dbUser}
                    onChange={(e) => setDbUser(e.target.value)}
                    className="w-full bg-black border border-[#27272a] rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-500"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1">Password</label>
                  <input
                    type="password"
                    required
                    placeholder="••••••••"
                    value={dbPass}
                    onChange={(e) => setDbPass(e.target.value)}
                    className="w-full bg-black border border-[#27272a] rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1">Table Name</label>
                <input
                  type="text"
                  required
                  placeholder="users"
                  value={dbTable}
                  onChange={(e) => setDbTable(e.target.value)}
                  className="w-full bg-black border border-[#27272a] rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-500"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowSqlModal(false)}
                  className="px-4 py-2 border border-[#27272a] hover:bg-[#1c1c1f] rounded-lg text-xs font-semibold text-zinc-400 hover:text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isConnectingDb}
                  className="px-5 py-2 bg-white hover:bg-zinc-200 disabled:bg-zinc-800 disabled:text-zinc-500 text-black text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5"
                >
                  {isConnectingDb ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Connecting...
                    </>
                  ) : (
                    "Establish Connection"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {showCreateInput && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[110] flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-[#121214] border border-[#27272a] rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#27272a]">
              <h3 className="text-lg font-bold text-white">Create New Workspace</h3>
              <button 
                onClick={() => setShowCreateInput(false)}
                className="text-zinc-400 hover:text-white p-1 rounded hover:bg-[#1c1c1f]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1.5">Workspace Name</label>
                <input
                  type="text"
                  placeholder="e.g. Sales Analysis Q2"
                  value={newSessionTitle}
                  onChange={(e) => setNewSessionTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && newSessionTitle.trim()) {
                      handleCreateSessionDirect();
                      setShowCreateInput(false);
                    } else if (e.key === "Escape") {
                      setShowCreateInput(false);
                    }
                  }}
                  className="w-full bg-black border border-[#27272a] rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-zinc-550 placeholder-zinc-700"
                  autoFocus
                />
              </div>
              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateInput(false)}
                  className="px-4 py-2 border border-[#27272a] hover:bg-[#1c1c1f] rounded-lg text-xs font-semibold text-zinc-400 hover:text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    handleCreateSessionDirect();
                    setShowCreateInput(false);
                  }}
                  disabled={!newSessionTitle.trim()}
                  className="px-5 py-2 bg-white hover:bg-zinc-200 disabled:bg-zinc-800 disabled:text-zinc-500 text-black text-xs font-bold rounded-lg transition"
                >
                  Create Workspace
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {showHelpModal && (
        <div className="fixed inset-0 bg-black/85 backdrop-blur-sm z-[150] flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-[#121214] border border-[#27272a] rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#27272a]">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-white" />
                <h3 className="text-lg font-bold text-white">Autonomous Data Agent Guide</h3>
              </div>
              <button 
                onClick={() => setShowHelpModal(false)}
                className="text-zinc-400 hover:text-white p-1 rounded hover:bg-[#1c1c1f]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4 text-sm text-zinc-300 leading-relaxed max-h-[400px] overflow-y-auto pr-1">
              <div>
                <h4 className="font-bold text-white mb-1">1. Setup your Workspace</h4>
                <p className="text-xs text-zinc-400">
                  Upload a dataset (CSV, JSON, Excel) using the drag-and-drop zone, or enter connection credentials for a PostgreSQL/MySQL database.
                </p>
              </div>
              <div>
                <h4 className="font-bold text-white mb-1">2. Run Calculations & Visualizations</h4>
                <p className="text-xs text-zinc-400">
                  Ask natural language questions. The AI agent compiles Python code, validates it inside a secure Docker execution sandbox, and registers output tables or visualization charts.
                </p>
              </div>
              <div>
                <h4 className="font-bold text-white mb-1">3. Redesigned Visual Analytics Pane</h4>
                <p className="text-xs text-zinc-400">
                  Click <strong>Code</strong> to expand the script, <strong>Discuss</strong> to focus and reply to a chart context, or <strong>Save</strong> to download the chart directly.
                </p>
              </div>
              <div>
                <h4 className="font-bold text-white mb-1">4. Rate Limits & Token Saving</h4>
                <p className="text-xs text-zinc-400">
                  Click the **Stop** button next to the input bar to cancel any active query. Large data outputs are automatically truncated to prevent unnecessary token usage.
                </p>
              </div>
            </div>
            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setShowHelpModal(false)}
                className="px-5 py-2.5 bg-white text-black hover:bg-zinc-200 text-xs font-bold rounded-lg transition"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
      {showDeleteConfirmModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[150] flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-[#121214] border border-[#27272a] rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#27272a]">
              <div className="flex items-center gap-2 text-red-400">
                <AlertTriangle className="w-5 h-5 animate-pulse" />
                <h3 className="text-lg font-bold text-white">Delete Dataset Source</h3>
              </div>
              <button 
                onClick={() => setShowDeleteConfirmModal(false)}
                className="text-zinc-400 hover:text-white p-1 rounded hover:bg-[#1c1c1f]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <p className="text-xs text-zinc-350 leading-relaxed">
              Are you sure you want to delete this dataset source? This will permanently clear all workspace messages and visualizations.
            </p>

            <div className="pt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowDeleteConfirmModal(false)}
                className="px-4 py-2 border border-[#27272a] hover:bg-[#1c1c1f] rounded-lg text-xs font-semibold text-zinc-400 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={async () => {
                  await handleDeleteDatasetSource();
                  setShowDeleteConfirmModal(false);
                }}
                className="px-5 py-2 bg-red-650 hover:bg-red-500 text-white text-xs font-bold rounded-lg transition"
              >
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}
      {zoomedChartUrl && (
        <div 
          onClick={() => setZoomedChartUrl(null)}
          className="fixed inset-0 bg-black/95 z-[200] flex items-center justify-center p-4 cursor-zoom-out animate-fade-in"
        >
          <div className="relative max-w-5xl max-h-[90vh] flex flex-col items-center">
            <img 
              src={zoomedChartUrl} 
              alt="Zoomed Visualization" 
              className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl border border-zinc-800"
            />
            <span className="mt-3 text-zinc-400 text-xs font-mono uppercase tracking-wider select-none">
              Click anywhere to dismiss
            </span>
          </div>
        </div>
      )}

    </div>
  );
}

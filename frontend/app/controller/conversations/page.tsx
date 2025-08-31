"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { getControllerUrl } from "@/lib/config";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  MessageSquare,
  RefreshCw,
  Trash2,
  LogOut,
  Shield,
  AlertTriangle,
  Clock,
  User,
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  Timer,
  Zap,
} from "lucide-react";

interface ConversationInfo {
  user_id: string;
  agent_type: string;
  session_id: string;
  last_activity: string | null;
  message_count: number;
  is_active: boolean;
  tenant_id?: string; // Optional for backward compatibility
  is_historical?: boolean; // True if from database (completed), False if from Redis (active)
}

interface ConversationsResponse {
  conversations: ConversationInfo[];
  total_count: number;
  active_count: number;
}

interface AgentThought {
  id: string;
  timestamp: string;
  user_message: string;
  reasoning: string;
  selected_tool: string;
  tool_args: Record<string, any>;
  tool_result?: string;
  agent_response?: string;
  errors?: string[];
  confidence?: number;
  processing_time_ms?: number;
  model_name: string;
}

interface ConversationTrace {
  user_id: string;
  session_id: string;
  agent_type: string;
  started_at: string;
  last_activity: string;
  total_thoughts: number;
  thoughts: AgentThought[];
  channel_id?: string; // Channel identifier for customer traceability
}

export default function ConversationsPage(): React.JSX.Element {
  const [conversations, setConversations] = useState<ConversationInfo[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [resetLoading, setResetLoading] = useState<string | null>(null);
  const [showResetDialog, setShowResetDialog] = useState(false);
  const [conversationToReset, setConversationToReset] = useState<ConversationInfo | null>(null);
  const [showTraceDialog, setShowTraceDialog] = useState(false);
  const [selectedTrace, setSelectedTrace] = useState<ConversationTrace | null>(null);
  const [traceLoading, setTraceLoading] = useState<string | null>(null);
  const [expandedThoughts, setExpandedThoughts] = useState<Set<string>>(new Set());
  const router = useRouter();

  const fetchConversations = useCallback(async (): Promise<void> => {
    try {
      const params = new URLSearchParams({
        active_only: activeOnly.toString(),
        limit: "100"
      });
      
      const response = await fetch(getControllerUrl(`/conversations?${params}`), {
        credentials: "include",
      });

      if (response.status === 401) {
        router.push("/controller");
        return;
      }

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to fetch conversations");
      }

      const data: ConversationsResponse = await response.json();
      setConversations(data.conversations);
      setTotalCount(data.total_count);
      setActiveCount(data.active_count);
    } catch (err) {
      console.error("Error loading conversations:", err);
      setError(err instanceof Error ? err.message : "Failed to load conversations. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [router, activeOnly]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const handleLogout = async (): Promise<void> => {
    try {
      await fetch(getControllerUrl("/logout"), {
        method: "POST",
        credentials: "include",
      });
      router.push("/controller");
    } catch {
      router.push("/controller");
    }
  };

  const handleResetConversation = async (conversation: ConversationInfo): Promise<void> => {
    const resetKey = `${conversation.user_id}:${conversation.agent_type}`;
    setResetLoading(resetKey);

    try {
      const response = await fetch(getControllerUrl("/conversations/reset"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          user_id: conversation.user_id,
          agent_type: conversation.agent_type,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to reset conversation");
      }

      // Refresh the conversations list
      await fetchConversations();
      setShowResetDialog(false);
      setConversationToReset(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset conversation");
    } finally {
      setResetLoading(null);
    }
  };

  const handleViewTrace = async (conversation: ConversationInfo): Promise<void> => {
    const conversationKey = `${conversation.user_id}:${conversation.agent_type}`;
    setTraceLoading(conversationKey);
    try {
      const tenant_id = conversation.tenant_id;
      
      if (!tenant_id) {
        setError("Could not determine tenant for this conversation. Trace functionality requires tenant information.");
        return;
      }

      // Extract the actual flow ID from the agent_type for trace lookup
      // Agent type format: "flow:whatsapp:5522988544370:flow.atendimento_luminarias" -> "flow.atendimento_luminarias"
      let traceAgentType = conversation.agent_type;
      if (conversation.agent_type.startsWith("flow:") && conversation.agent_type.includes(":flow.")) {
        traceAgentType = "flow." + conversation.agent_type.split(":flow.")[1];
      }

      const params = new URLSearchParams({ 
        tenant_id, 
        user_id: conversation.user_id 
      });
      const response = await fetch(getControllerUrl(`/traces/${encodeURIComponent(traceAgentType)}?${params}`), {
        credentials: "include",
      });

      if (response.status === 404) {
        setError("No reasoning trace found for this conversation");
        return;
      }

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to fetch conversation trace");
      }

      const trace: ConversationTrace = await response.json();
      setSelectedTrace(trace);
      setShowTraceDialog(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch conversation trace");
    } finally {
      setTraceLoading(null);
    }
  };

  const toggleThoughtExpansion = (thoughtId: string): void => {
    const newExpanded = new Set(expandedThoughts);
    if (newExpanded.has(thoughtId)) {
      newExpanded.delete(thoughtId);
    } else {
      newExpanded.add(thoughtId);
    }
    setExpandedThoughts(newExpanded);
  };

  const formatLastActivity = (timestamp: string | null): string => {
    if (!timestamp) return "Never";
    
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffHours < 1) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      return `${diffMinutes}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else if (diffDays < 7) {
      return `${diffDays}d ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  const navigateToTenants = () => {
    router.push("/controller/tenants");
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading conversations...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <div className="h-8 w-8 flex items-center justify-center rounded-full bg-blue-100">
              <Shield className="h-4 w-4 text-blue-600" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Conversation Management</h1>
          </div>
          <div className="flex space-x-2">
            <Button onClick={navigateToTenants} variant="outline">
              Back to Tenants
            </Button>
            <Button onClick={handleLogout} variant="outline">
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <MessageSquare className="h-8 w-8 text-blue-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">Total Conversations</p>
                  <p className="text-2xl font-bold text-gray-900">{totalCount}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <Clock className="h-8 w-8 text-green-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">Active (24h)</p>
                  <p className="text-2xl font-bold text-gray-900">{activeCount}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <Bot className="h-8 w-8 text-purple-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">Displayed</p>
                  <p className="text-2xl font-bold text-gray-900">{conversations.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Controls */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Button
              variant={activeOnly ? "default" : "outline"}
              onClick={() => setActiveOnly(!activeOnly)}
            >
              {activeOnly ? "Show All" : "Show Active Only"}
            </Button>
          </div>
          <Button onClick={fetchConversations} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>

        {/* Conversations Table */}
        <Card>
          <CardHeader>
            <CardTitle>Conversations </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User ID</TableHead>
                  <TableHead>Flow Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Messages</TableHead>
                  <TableHead>Last Activity</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {conversations.map((conversation, index) => {
                  return (
                  <TableRow key={`${conversation.user_id}-${conversation.agent_type}-${index}`}>
                    <TableCell className="max-w-48">
                      <div className="flex items-center">
                        <User className="h-4 w-4 mr-2 text-gray-400 flex-shrink-0" />
                        <div className="min-w-0">
                          <p className="font-medium truncate">{conversation.user_id}</p>
                          <p className="text-sm text-gray-500 truncate">{conversation.session_id}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-64">
                      <Badge variant="outline" className="truncate max-w-full">{conversation.agent_type}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={conversation.is_active ? "default" : "secondary"}>
                        {conversation.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>{conversation.message_count}</TableCell>
                    <TableCell>
                      {formatLastActivity(conversation.last_activity)}
                    </TableCell>
                    <TableCell>
                      <div className="flex space-x-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleViewTrace(conversation)}
                          disabled={traceLoading === `${conversation.user_id}:${conversation.agent_type}`}
                          className="text-blue-600 hover:text-blue-700"
                          title="View reasoning trace"
                        >
                          {traceLoading === `${conversation.user_id}:${conversation.agent_type}` ? (
                            <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-600" />
                          ) : (
                            <Brain className="h-3 w-3" />
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setConversationToReset(conversation);
                            setShowResetDialog(true);
                          }}
                          disabled={resetLoading === `${conversation.user_id}:${conversation.agent_type}` || conversation.is_historical}
                          className={conversation.is_historical ? "text-gray-400" : "text-orange-600 hover:text-orange-700"}
                          title={conversation.is_historical ? "Historical conversation (read-only)" : "Reset conversation context"}
                        >
                          {resetLoading === `${conversation.user_id}:${conversation.agent_type}` ? (
                            <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-orange-600" />
                          ) : (
                            <RefreshCw className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            {conversations.length === 0 && (
              <div className="text-center py-8">
                <p className="text-gray-500">
                  {activeOnly 
                    ? "No active conversations found. Try showing all conversations." 
                    : "No conversations found."
                  }
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Reset Confirmation Dialog */}
        <Dialog open={showResetDialog} onOpenChange={setShowResetDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Reset Conversation Context</DialogTitle>
            </DialogHeader>
            {conversationToReset && (
              <div className="space-y-4">
                <p>
                  Are you sure you want to reset the Redis context for:
                </p>
                <div className="bg-gray-50 p-4 rounded-lg">
                  <p><strong>User ID:</strong> {conversationToReset.user_id}</p>
                  <p><strong>Agent Type:</strong> {conversationToReset.agent_type}</p>
                  <p><strong>Messages:</strong> {conversationToReset.message_count}</p>
                  <p><strong>Status:</strong> {conversationToReset.is_active ? "Active" : "Inactive"}</p>
                </div>
                <p className="text-sm text-gray-600">
                  This will clear the Redis conversation context, allowing the user to restart the flow. 
                  All debugging data (traces, messages) will be preserved in the database.
                </p>
                <div className="flex justify-end space-x-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowResetDialog(false);
                      setConversationToReset(null);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="default"
                    onClick={() => handleResetConversation(conversationToReset)}
                    disabled={resetLoading !== null}
                    className="bg-orange-600 hover:bg-orange-700 text-white"
                  >
                    {resetLoading ? "Resetting..." : "Reset Context"}
                  </Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* Reasoning Trace Dialog */}
        <Dialog open={showTraceDialog} onOpenChange={setShowTraceDialog}>
          <DialogContent className="max-w-[95vw] w-full max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Agent Reasoning Trace</DialogTitle>
            </DialogHeader>
            {selectedTrace && (
              <div className="space-y-4">
                <div className="bg-gray-50 p-4 rounded-lg">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p><strong>User ID:</strong> {selectedTrace.user_id}</p>
                      <p><strong>Agent Type:</strong> {selectedTrace.agent_type}</p>
                      <p><strong>Session ID:</strong> {selectedTrace.session_id}</p>
                      {selectedTrace.channel_id && (
                        <p><strong>Channel ID:</strong> {selectedTrace.channel_id}</p>
                      )}
                    </div>
                    <div>
                      <p><strong>Started:</strong> {new Date(selectedTrace.started_at).toLocaleString()}</p>
                      <p><strong>Last Activity:</strong> {new Date(selectedTrace.last_activity).toLocaleString()}</p>
                      <p><strong>Total Thoughts:</strong> {selectedTrace.total_thoughts}</p>
                    </div>
                  </div>
                </div>

                {selectedTrace.thoughts.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-gray-500">No reasoning traces found for this conversation.</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {selectedTrace.thoughts.map((thought, index) => (
                      <div key={thought.id} className="border rounded-lg p-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-2">
                            <span className="text-sm font-medium text-gray-500">
                              Thought #{index + 1}
                            </span>
                            <Badge variant="outline">{thought.selected_tool}</Badge>
                            {thought.processing_time_ms && (
                              <div className="flex items-center text-xs text-gray-500">
                                <Timer className="h-3 w-3 mr-1" />
                                {thought.processing_time_ms}ms
                              </div>
                            )}
                            {thought.confidence && (
                              <div className="flex items-center text-xs text-gray-500">
                                <Zap className="h-3 w-3 mr-1" />
                                {Math.round(thought.confidence * 100)}%
                              </div>
                            )}
                          </div>
                          <div className="text-xs text-gray-500">
                            {new Date(thought.timestamp).toLocaleString()}
                          </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <p className="text-sm font-medium text-gray-700 mb-1">User Message:</p>
                            <p className="text-sm bg-blue-50 p-2 rounded border-l-4 border-blue-200">
                              {thought.user_message}
                            </p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-gray-700 mb-1">Agent Reasoning:</p>
                            <p className="text-sm bg-green-50 p-2 rounded border-l-4 border-green-200">
                              {thought.reasoning}
                            </p>
                          </div>
                        </div>

                        {thought.errors && thought.errors.length > 0 && (
                          <div>
                            <p className="text-sm font-medium text-red-700 mb-1">Errors:</p>
                            <div className="bg-red-50 p-2 rounded border-l-4 border-red-200">
                              {thought.errors.map((error, i) => (
                                <p key={i} className="text-sm text-red-600">{error}</p>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="border-t pt-3">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleThoughtExpansion(thought.id)}
                            className="flex items-center space-x-1"
                          >
                            {expandedThoughts.has(thought.id) ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                            <span>
                              {expandedThoughts.has(thought.id) ? "Hide" : "Show"} Details
                            </span>
                          </Button>

                          {expandedThoughts.has(thought.id) && (
                            <div className="mt-3 space-y-3">
                              <div>
                                <p className="text-sm font-medium text-gray-700 mb-1">Tool Arguments:</p>
                                <pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto whitespace-pre-wrap break-words max-h-32">
                                  {JSON.stringify(thought.tool_args, null, 2)}
                                </pre>
                              </div>

                              {thought.tool_result && (
                                <div>
                                  <p className="text-sm font-medium text-gray-700 mb-1">Tool Result:</p>
                                  <p className="text-sm bg-yellow-50 p-2 rounded border-l-4 border-yellow-200 max-h-32 overflow-y-auto">
                                    {thought.tool_result}
                                  </p>
                                </div>
                              )}

                              {thought.agent_response && (
                                <div>
                                  <p className="text-sm font-medium text-gray-700 mb-1">Agent Response:</p>
                                  <p className="text-sm bg-purple-50 p-2 rounded border-l-4 border-purple-200">
                                    {thought.agent_response}
                                  </p>
                                </div>
                              )}

                              <div className="text-xs text-gray-500 flex items-center space-x-4">
                                <span>Model: {thought.model_name}</span>
                                <span>ID: {thought.id}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowTraceDialog(false);
                      setSelectedTrace(null);
                      setExpandedThoughts(new Set());
                    }}
                  >
                    Close
                  </Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}

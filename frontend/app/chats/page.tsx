"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, type ChatThread } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { toast } from "sonner";
import { 
  MessageCircle, 
  Clock, 
  User, 
  Phone, 
  Check, 
  CheckCheck, 
  AlertCircle, 
  Archive,
  RefreshCw,
  Search,
  Filter,
  MessageSquare
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// Format date to relative time
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  
  const minutes = Math.floor(diff / (1000 * 60));
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  
  if (minutes < 1) return "Agora mesmo";
  if (minutes < 60) return `${minutes}m atrás`;
  if (hours < 24) return `${hours}h atrás`;
  if (days < 7) return `${days}d atrás`;
  
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined
  });
}

// Format phone number for display
function formatPhoneNumber(phone: string | undefined): string {
  if (!phone) return "";
  // Remove non-digits and format as Brazilian phone
  const digits = phone.replace(/\D/g, "");
  if (digits.length === 13 && digits.startsWith("55")) {
    // Brazilian international format
    const local = digits.slice(2);
    return `+55 (${local.slice(0,2)}) ${local.slice(2,7)}-${local.slice(7)}`;
  }
  return phone;
}

// Get status color and icon
function getStatusDisplay(status: ChatThread['status']) {
  switch (status) {
    case 'open':
      return {
        color: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
        icon: MessageCircle,
        label: 'Ativo'
      };
    case 'closed':
      return {
        color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
        icon: Check,
        label: 'Concluído'
      };
    case 'archived':
      return {
        color: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
        icon: Archive,
        label: 'Arquivado'
      };
    default:
      return {
        color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
        icon: AlertCircle,
        label: status
      };
  }
}

// Chat interaction card component
function ChatCard({ thread, onClick }: { thread: ChatThread; onClick: () => void }) {
  const statusDisplay = getStatusDisplay(thread.status);
  const StatusIcon = statusDisplay.icon;
  
  return (
    <div 
      onClick={onClick}
      className="group relative cursor-pointer overflow-hidden rounded-2xl border bg-card hover:bg-accent/50 transition-all duration-300 hover:shadow-lg hover:shadow-brand-200/20 hover:-translate-y-1 animate-bounce-in"
    >
      {/* Status indicator bar */}
      <div className={`absolute left-0 top-0 w-1 h-full ${
        thread.status === 'open' ? 'bg-brand-500' : 
        thread.status === 'closed' ? 'bg-gray-400' : 'bg-amber-500'
      }`} />
      
      <div className="p-6 pl-8">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            {/* Avatar */}
            <div className="relative">
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white font-medium shadow-lg">
                {thread.contact.display_name ? 
                  thread.contact.display_name.slice(0, 2).toUpperCase() :
                  <User className="w-5 h-5" />
                }
              </div>
              {thread.status === 'open' && (
                <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 bg-emerald-500 rounded-full border-2 border-white animate-pulse" />
              )}
            </div>
            
            {/* Contact info */}
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-foreground group-hover:text-brand-700 transition-colors">
                {thread.contact.display_name || "Cliente"}
              </h3>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                {thread.contact.phone_number && (
                  <div className="flex items-center gap-1">
                    <Phone className="w-3 h-3" />
                    <span>{formatPhoneNumber(thread.contact.phone_number)}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
          
          {/* Status badge */}
          <Badge className={`${statusDisplay.color} border-0 font-medium px-3 py-1`}>
            <StatusIcon className="w-3 h-3 mr-1.5" />
            {statusDisplay.label}
          </Badge>
        </div>

        {/* Subject if available */}
        {thread.subject && (
          <div className="mb-3">
            <p className="text-sm font-medium text-foreground">{thread.subject}</p>
          </div>
        )}

        {/* Conversation metadata */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-4 text-muted-foreground">
            <div className="flex items-center gap-1">
              <MessageSquare className="w-4 h-4" />
              <span>Conversa</span>
            </div>
            <div className="flex items-center gap-1">
              <Clock className="w-4 h-4" />
              <span>
                {thread.last_message_at 
                  ? formatRelativeTime(thread.last_message_at)
                  : formatRelativeTime(thread.created_at)
                }
              </span>
            </div>
          </div>
          
          {/* Hover arrow */}
          <div className="text-brand-500 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </div>
        </div>

        {/* Visual enhancement gradient */}
        <div className="absolute inset-0 bg-gradient-to-r from-brand-50/0 via-brand-50/0 to-brand-50/30 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none dark:from-brand-950/0 dark:via-brand-950/0 dark:to-brand-950/30" />
      </div>
    </div>
  );
}

export default function ChatsPage() {
  const router = useRouter();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | ChatThread['status']>("all");
  const [refreshing, setRefreshing] = useState(false);

  // Load chat threads
  const loadThreads = async (showRefreshing = false) => {
    try {
      if (showRefreshing) setRefreshing(true);
      const data = await api.chats.listThreads(undefined, { limit: 100 });
      setThreads(data);
    } catch (error) {
      console.error("Failed to load chat threads:", error);
      toast.error("Erro ao carregar conversas");
    } finally {
      setLoading(false);
      if (showRefreshing) setRefreshing(false);
    }
  };

  useEffect(() => {
    loadThreads();
  }, []);

  // Filter threads based on search and status
  const filteredThreads = threads.filter(thread => {
    const matchesSearch = !searchQuery || 
      thread.contact.display_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      thread.contact.phone_number?.includes(searchQuery) ||
      thread.subject?.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesStatus = statusFilter === "all" || thread.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  // Navigate to individual chat
  const handleChatClick = (threadId: string) => {
    router.push(`/chats/${threadId}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-4 border-brand-200 border-t-brand-600 rounded-full animate-spin" />
          <p className="text-muted-foreground">Carregando conversas...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto p-6">
      <PageHeader
        title="Conversas com Clientes"
        subtitle="Gerencie todas as interações com seus clientes"
        actions={
          <Button 
            onClick={() => loadThreads(true)} 
            disabled={refreshing}
            variant="outline"
            size="sm"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
        }
      />

      {/* Filters and search */}
      <div className="flex flex-col sm:flex-row gap-4 items-stretch sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Buscar por nome, telefone ou assunto..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        
        <Select value={statusFilter} onValueChange={(value: typeof statusFilter) => setStatusFilter(value)}>
          <SelectTrigger className="w-full sm:w-[180px]">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Filtrar por status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os status</SelectItem>
            <SelectItem value="open">Ativo</SelectItem>
            <SelectItem value="closed">Concluído</SelectItem>
            <SelectItem value="archived">Arquivado</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-brand-50 to-brand-100 dark:from-brand-950 dark:to-brand-900 p-4 rounded-xl border border-brand-200 dark:border-brand-800">
          <div className="text-2xl font-bold text-brand-700 dark:text-brand-300">
            {threads.length}
          </div>
          <div className="text-sm text-brand-600 dark:text-brand-400">Total</div>
        </div>
        <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 dark:from-emerald-950 dark:to-emerald-900 p-4 rounded-xl border border-emerald-200 dark:border-emerald-800">
          <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">
            {threads.filter(t => t.status === 'open').length}
          </div>
          <div className="text-sm text-emerald-600 dark:text-emerald-400">Ativas</div>
        </div>
        <div className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-950 dark:to-gray-900 p-4 rounded-xl border border-gray-200 dark:border-gray-800">
          <div className="text-2xl font-bold text-gray-700 dark:text-gray-300">
            {threads.filter(t => t.status === 'closed').length}
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400">Concluídas</div>
        </div>
        <div className="bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-950 dark:to-amber-900 p-4 rounded-xl border border-amber-200 dark:border-amber-800">
          <div className="text-2xl font-bold text-amber-700 dark:text-amber-300">
            {threads.filter(t => t.status === 'archived').length}
          </div>
          <div className="text-sm text-amber-600 dark:text-amber-400">Arquivadas</div>
        </div>
      </div>

      {/* Chat cards */}
      {filteredThreads.length === 0 ? (
        <div className="text-center py-12">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-brand-100 dark:bg-brand-900 flex items-center justify-center">
            <MessageCircle className="w-8 h-8 text-brand-600 dark:text-brand-400" />
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">
            {searchQuery || statusFilter !== "all" ? "Nenhuma conversa encontrada" : "Nenhuma conversa ainda"}
          </h3>
          <p className="text-muted-foreground max-w-md mx-auto">
            {searchQuery || statusFilter !== "all" 
              ? "Tente ajustar os filtros para encontrar as conversas que procura."
              : "As conversas com seus clientes aparecerão aqui quando chegarem mensagens."
            }
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:gap-6">
          {filteredThreads.map((thread) => (
            <ChatCard
              key={thread.id}
              thread={thread}
              onClick={() => handleChatClick(thread.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

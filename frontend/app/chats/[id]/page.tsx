"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { api, type ChatThread, type Message } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { 
  ArrowLeft, 
  MessageCircle, 
  Clock, 
  User, 
  Phone, 
  Check, 
  CheckCheck,
  Archive,
  RefreshCw,
  ExternalLink,
  Copy,
  MoreVertical,
  AlertCircle
} from "lucide-react";

// Format date to readable format
function formatDateTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = date.toDateString() === yesterday.toDateString();
  
  const timeStr = date.toLocaleTimeString("pt-BR", { 
    hour: "2-digit", 
    minute: "2-digit" 
  });
  
  if (isToday) return `Hoje às ${timeStr}`;
  if (isYesterday) return `Ontem às ${timeStr}`;
  
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined
  }) + ` às ${timeStr}`;
}

// Format phone number for display
function formatPhoneNumber(phone: string | undefined): string {
  if (!phone) return "";
  const digits = phone.replace(/\D/g, "");
  if (digits.length === 13 && digits.startsWith("55")) {
    const local = digits.slice(2);
    return `+55 (${local.slice(0,2)}) ${local.slice(2,7)}-${local.slice(7)}`;
  }
  return phone;
}

// Get status display
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

// Message component
function MessageBubble({ message }: { message: Message }) {
  const isInbound = message.direction === 'inbound';
  
  const getDeliveryIcon = () => {
    if (message.direction === 'inbound') return null;
    
    if (message.read_at) {
      return <CheckCheck className="w-3 h-3 text-blue-500" />;
    } else if (message.delivered_at) {
      return <CheckCheck className="w-3 h-3 text-gray-400" />;
    } else if (message.sent_at) {
      return <Check className="w-3 h-3 text-gray-400" />;
    }
    return <Clock className="w-3 h-3 text-gray-400" />;
  };

  return (
    <div className={`flex w-full mb-4 ${isInbound ? 'justify-start' : 'justify-end'}`}>
      <div className={`max-w-[70%] min-w-[120px] rounded-2xl px-4 py-3 shadow-sm ${
        isInbound 
          ? 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-tl-none text-gray-900 dark:text-gray-100' 
          : 'bg-gradient-to-br from-brand-500 to-brand-600 text-white rounded-tr-none'
      }`}>
        <div className="text-sm leading-relaxed whitespace-pre-wrap mb-2">
          {message.text}
        </div>
        
        <div className={`flex items-center justify-between text-xs ${
          isInbound ? 'text-gray-500 dark:text-gray-400' : 'text-brand-100'
        }`}>
          <span>{formatDateTime(message.created_at)}</span>
          {getDeliveryIcon()}
        </div>
      </div>
    </div>
  );
}

export default function ChatDetailPage() {
  const router = useRouter();
  const params = useParams();
  const threadId = params.id as string;
  
  const [thread, setThread] = useState<ChatThread | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load thread details
  const loadThread = async (showRefreshing = false) => {
    try {
      if (showRefreshing) setRefreshing(true);
      const data = await api.chats.getThread(undefined, threadId);
      setThread(data);
      setError(null);
    } catch (error) {
      console.error("Failed to load thread:", error);
      setError("Erro ao carregar conversa");
      toast.error("Erro ao carregar conversa");
    } finally {
      setLoading(false);
      if (showRefreshing) setRefreshing(false);
    }
  };

  useEffect(() => {
    if (threadId) {
      loadThread();
    }
  }, [threadId]);

  // Copy contact info to clipboard
  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copiado para a área de transferência`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-4 border-brand-200 border-t-brand-600 rounded-full animate-spin" />
          <p className="text-muted-foreground">Carregando conversa...</p>
        </div>
      </div>
    );
  }

  if (error || !thread) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900 flex items-center justify-center">
          <AlertCircle className="w-8 h-8 text-red-600 dark:text-red-400" />
        </div>
        <h2 className="text-xl font-semibold">Conversa não encontrada</h2>
        <p className="text-muted-foreground text-center max-w-md">
          Não foi possível carregar esta conversa. Ela pode ter sido removida ou você pode não ter permissão para visualizá-la.
        </p>
        <Button onClick={() => router.push('/chats')} variant="outline">
          <ArrowLeft className="w-4 h-4 mr-2" />
          Voltar às conversas
        </Button>
      </div>
    );
  }

  const statusDisplay = getStatusDisplay(thread.status);
  const StatusIcon = statusDisplay.icon;

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {/* Header */}
      <PageHeader
        title={
          <div className="flex items-center gap-4">
            <Button 
              onClick={() => router.push('/chats')} 
              variant="ghost" 
              size="sm"
              className="p-2"
            >
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div>
              <h1 className="text-2xl font-bold">
                {thread.contact.display_name || "Cliente"}
              </h1>
              {thread.subject && (
                <p className="text-muted-foreground text-sm mt-1">{thread.subject}</p>
              )}
            </div>
          </div>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge className={`${statusDisplay.color} border-0 font-medium px-3 py-2`}>
              <StatusIcon className="w-4 h-4 mr-2" />
              {statusDisplay.label}
            </Badge>
            <Button 
              onClick={() => loadThread(true)} 
              disabled={refreshing}
              variant="outline"
              size="sm"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        }
      />

      {/* Contact info panel */}
      <div className="bg-card border rounded-2xl p-6">
        <div className="flex items-start gap-4">
          {/* Avatar */}
          <div className="relative">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white font-medium text-lg shadow-lg">
              {thread.contact.display_name ? 
                thread.contact.display_name.slice(0, 2).toUpperCase() :
                <User className="w-6 h-6" />
              }
            </div>
            {thread.status === 'open' && (
              <div className="absolute -bottom-1 -right-1 w-5 h-5 bg-emerald-500 rounded-full border-2 border-white" />
            )}
          </div>

          {/* Contact details */}
          <div className="flex-1 space-y-3">
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                {thread.contact.display_name || "Cliente"}
              </h2>
              <p className="text-sm text-muted-foreground">
                Conversa iniciada em {formatDateTime(thread.created_at)}
              </p>
            </div>

            <div className="flex flex-wrap gap-4">
              {thread.contact.phone_number && (
                <button
                  onClick={() => copyToClipboard(thread.contact.phone_number!, 'Telefone')}
                  className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
                >
                  <Phone className="w-4 h-4" />
                  <span>{formatPhoneNumber(thread.contact.phone_number)}</span>
                  <Copy className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
              )}
              
              <button
                onClick={() => copyToClipboard(thread.contact.external_id, 'ID do contato')}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
              >
                <ExternalLink className="w-4 h-4" />
                <span>ID: {thread.contact.external_id.split(':')[1]?.slice(-8) || thread.contact.external_id}</span>
                <Copy className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
            </div>

            {/* Timestamps */}
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                <span>Última mensagem: {thread.last_message_at ? formatDateTime(thread.last_message_at) : 'Nenhuma'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="bg-card border rounded-2xl">
        <div className="p-4 border-b">
          <h3 className="font-semibold flex items-center gap-2">
            <MessageCircle className="w-5 h-5 text-brand-600" />
            Mensagens
            {thread.messages && (
              <Badge variant="secondary" className="ml-2">
                {thread.messages.length}
              </Badge>
            )}
          </h3>
        </div>
        
        <div className="p-6">
          {thread.messages && thread.messages.length > 0 ? (
            <div className="space-y-1">
              {thread.messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                <MessageCircle className="w-8 h-8 text-gray-400" />
              </div>
              <h4 className="text-lg font-medium text-foreground mb-2">Nenhuma mensagem</h4>
              <p className="text-muted-foreground">
                Esta conversa ainda não tem mensagens registradas.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState, useEffect } from "react";
import { Bot, Settings, User, Globe, MessageCircle, Clock, ArrowRight, TrendingUp, Users, CheckCircle, BarChart3, Smartphone } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { api, type ChatThread } from "@/lib/api-client";
import { toast } from "sonner";

const shortcuts = [
  { href: "/analytics", icon: BarChart3, label: "Analytics", description: "Insights e métricas de performance de vendas" },
  { href: "/chats", icon: MessageCircle, label: "Conversas", description: "Visualizar e gerenciar conversas com clientes" },
  { href: "/flows", icon: Bot, label: "Fluxos", description: "Gerenciar fluxos e agentes relacionados" },
  { href: "/channels", icon: Smartphone, label: "Canais", description: "Gerenciar canais do WhatsApp e fluxos ativos" },
  { href: "/account", icon: User, label: "Conta", description: "Informações pessoais" },
  { href: "/project", icon: Globe, label: "Configurações Globais", description: "Definições padrão para todos os fluxos" },
  { href: "/settings", icon: Settings, label: "Configurações", description: "Preferências e configuração do app" },
];

// Format date to relative time
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  
  const minutes = Math.floor(diff / (1000 * 60));
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  
  if (minutes < 1) return "Agora mesmo";
  if (minutes < 60) return `${minutes}m`;
  if (hours < 24) return `${hours}h`;
  if (days < 7) return `${days}d`;
  
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short"
  });
}

// Recent chat card component
function RecentChatCard({ thread }: { thread: ChatThread }) {
  const isActive = thread.status === 'open';
  
  return (
    <Link href={`/chats/${thread.id}`} className="group">
      <div className="flex items-center gap-3 p-3 rounded-xl hover:bg-accent/50 transition-all duration-200 border border-transparent hover:border-brand-200 hover:shadow-sm">
        <div className="relative">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white font-medium text-sm">
            {thread.contact.display_name ? 
              thread.contact.display_name.slice(0, 2).toUpperCase() :
              <User className="w-4 h-4" />
            }
          </div>
          {isActive && (
            <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 rounded-full border-2 border-white" />
          )}
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h4 className="font-medium text-foreground group-hover:text-brand-700 transition-colors truncate">
              {thread.contact.display_name || "Cliente"}
            </h4>
            <span className="text-xs text-muted-foreground ml-2 flex-shrink-0">
              {thread.last_message_at ? formatRelativeTime(thread.last_message_at) : formatRelativeTime(thread.created_at)}
            </span>
          </div>
          <div className="flex items-center justify-between mt-1">
            <p className="text-sm text-muted-foreground truncate">
              {thread.subject || "Nova conversa"}
            </p>
            <Badge 
              variant="secondary" 
              className={`ml-2 text-xs ${isActive ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600'}`}
            >
              {isActive ? 'Ativo' : thread.status === 'closed' ? 'Concluído' : 'Arquivado'}
            </Badge>
          </div>
        </div>
        
        <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </Link>
  );
}

export default function Home() {
  const [recentThreads, setRecentThreads] = useState<ChatThread[]>([]);
  const [chatStats, setChatStats] = useState({
    total: 0,
    active: 0,
    closed: 0,
    loading: true
  });

  // Load recent chats and stats
  useEffect(() => {
    const loadChatsData = async () => {
      try {
        const threads = await api.chats.listThreads(undefined, { limit: 5 });
        setRecentThreads(threads);
        setChatStats({
          total: threads.length,
          active: threads.filter(t => t.status === 'open').length,
          closed: threads.filter(t => t.status === 'closed').length,
          loading: false
        });
      } catch (error) {
        console.error("Failed to load chats data:", error);
        setChatStats(prev => ({ ...prev, loading: false }));
      }
    };

    loadChatsData();
  }, []);

  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-6xl px-4 py-6 md:py-8">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-lg bg-primary/10 ring-1 ring-primary/20 grid place-items-center">
              <Bot className="h-6 w-6 text-primary" />
            </div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Inboxed</h1>
          </div>
          <p className="text-muted-foreground">Agentes de IA para automatizar sua caixa de entrada no WhatsApp</p>
        </div>

        {/* Chat Stats Overview */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-brand-100 dark:bg-brand-900">
                <MessageCircle className="w-4 h-4 text-brand-600 dark:text-brand-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-brand-700 dark:text-brand-300">
                  {chatStats.loading ? "—" : chatStats.total}
                </p>
                <p className="text-xs text-muted-foreground">Total</p>
              </div>
            </div>
          </Card>
          
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900">
                <Users className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">
                  {chatStats.loading ? "—" : chatStats.active}
                </p>
                <p className="text-xs text-muted-foreground">Ativas</p>
              </div>
            </div>
          </Card>
          
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900">
                <CheckCircle className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">
                  {chatStats.loading ? "—" : chatStats.closed}
                </p>
                <p className="text-xs text-muted-foreground">Concluídas</p>
              </div>
            </div>
          </Card>
          
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900">
                <TrendingUp className="w-4 h-4 text-purple-600 dark:text-purple-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                  {chatStats.loading ? "—" : Math.round((chatStats.closed / Math.max(chatStats.total, 1)) * 100)}%
                </p>
                <p className="text-xs text-muted-foreground">Taxa de conclusão</p>
              </div>
            </div>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Quick Actions */}
          <div className="lg:col-span-2">
            <h2 className="text-lg font-semibold mb-4">Acesso Rápido</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {shortcuts.map((shortcut) => {
                const Icon = shortcut.icon;
                return (
                  <Link key={shortcut.href} href={shortcut.href} className="group">
                    <Card className="p-4 hover:shadow-md transition-all duration-200 group-hover:border-primary/20 group-hover:bg-accent/30">
                      <div className="flex items-center gap-4">
                        <div className="h-12 w-12 rounded-xl bg-primary/10 ring-1 ring-primary/20 grid place-items-center group-hover:bg-primary/15 transition-colors">
                          <Icon className="h-6 w-6 text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="font-semibold group-hover:text-primary transition-colors">
                            {shortcut.label}
                          </h3>
                          <p className="text-sm text-muted-foreground truncate">
                            {shortcut.description}
                          </p>
                        </div>
                      </div>
                    </Card>
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Recent Conversations */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <MessageCircle className="w-5 h-5 text-brand-600" />
                    Conversas Recentes
                  </CardTitle>
                  <Link 
                    href="/chats" 
                    className="flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors px-2 py-1 rounded hover:bg-muted"
                  >
                    Ver todas
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {chatStats.loading ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="w-6 h-6 border-2 border-brand-200 border-t-brand-600 rounded-full animate-spin" />
                  </div>
                ) : recentThreads.length > 0 ? (
                  <div className="space-y-1 px-6 pb-6">
                    {recentThreads.map((thread) => (
                      <RecentChatCard key={thread.id} thread={thread} />
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12 px-6">
                    <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-brand-100 dark:bg-brand-900 flex items-center justify-center">
                      <MessageCircle className="w-6 h-6 text-brand-600 dark:text-brand-400" />
                    </div>
                    <h4 className="font-medium text-foreground mb-1">Nenhuma conversa ainda</h4>
                    <p className="text-sm text-muted-foreground">
                      As conversas com clientes aparecerão aqui
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

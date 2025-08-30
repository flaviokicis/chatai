"use client";

import { useState, useEffect } from "react";
import { Smartphone, Bot, Settings, Check, AlertCircle, Phone, Globe, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api-client";
import { toast } from "sonner";
import Link from "next/link";

interface Channel {
  id: string;
  channel_type: "whatsapp";
  identifier: string;
  phone_number: string | null;
  flows: Flow[];
}

interface Flow {
  id: string;
  name: string;
  flow_id: string;
  channel_instance_id: string;
  is_active: boolean;
}

function ChannelCard({ channel, onFlowChange }: { channel: Channel; onFlowChange: (channelId: string, flowId: string) => Promise<void> }) {
  const [isUpdating, setIsUpdating] = useState(false);
  const activeFlow = channel.flows.find(flow => flow.is_active);
  
  const handleFlowChange = async (flowId: string) => {
    if (isUpdating || flowId === activeFlow?.id) return;
    
    setIsUpdating(true);
    try {
      await onFlowChange(channel.id, flowId);
      toast.success("Fluxo ativo atualizado com sucesso!");
    } catch (error) {
      toast.error("Erro ao atualizar fluxo ativo");
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-emerald-100 dark:bg-emerald-900 flex items-center justify-center">
              <Smartphone className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <CardTitle className="text-lg">
                {channel.phone_number || channel.identifier}
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                {channel.channel_type === "whatsapp" ? "WhatsApp" : channel.channel_type}
              </p>
            </div>
          </div>
          <Badge 
            variant={activeFlow ? "default" : "secondary"} 
            className={activeFlow ? "bg-emerald-500 text-white" : ""}
          >
            <Bot className="w-3 h-3 mr-1" />
            {activeFlow ? "Ativo" : "Sem fluxo"}
          </Badge>
        </div>
      </CardHeader>
      
      <CardContent className="pt-0">
        {channel.flows.length > 0 ? (
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium text-foreground mb-2 block">
                Fluxo Ativo
              </label>
              <Select 
                value={activeFlow?.id || ""} 
                onValueChange={handleFlowChange}
                disabled={isUpdating}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selecione um fluxo" />
                </SelectTrigger>
                <SelectContent>
                  {channel.flows.map(flow => (
                    <SelectItem key={flow.id} value={flow.id}>
                      <div className="flex items-center gap-2">
                        <Bot className="w-4 h-4" />
                        <span>{flow.name}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            {activeFlow && (
              <div className="p-3 bg-emerald-50 dark:bg-emerald-950 rounded-lg border border-emerald-200 dark:border-emerald-800">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300 text-sm font-medium">
                      <Check className="w-4 h-4" />
                      Fluxo ativo: {activeFlow.name}
                    </div>
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                      ID: {activeFlow.flow_id}
                    </p>
                  </div>
                  <Link href={`/flows/${activeFlow.id}`}>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 px-2 bg-white dark:bg-emerald-900 border-emerald-300 dark:border-emerald-700 hover:bg-emerald-100 dark:hover:bg-emerald-800"
                      title="Ver fluxo"
                    >
                      <ExternalLink className="w-3 h-3" />
                    </Button>
                  </Link>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-6">
            <AlertCircle className="w-8 h-8 mx-auto mb-2 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Nenhum fluxo disponível para este canal
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Crie um fluxo na seção Fluxos primeiro
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);

  const loadChannels = async () => {
    try {
      setLoading(true);
      // Get channels first
      const channelInstances = await api.admin.listChannels();
      
      // Load flows for each channel
      const channelsWithFlows = await Promise.all(
        channelInstances.map(async (channel) => {
          try {
            const channelDetails = await api.admin.getChannelWithFlows(channel.id);
            return channelDetails;
          } catch (error) {
            console.error(`Failed to load flows for channel ${channel.id}:`, error);
            // Return channel without flows if we can't load them
            return {
              ...channel,
              flows: []
            };
          }
        })
      );
      
      setChannels(channelsWithFlows);
    } catch (error) {
      console.error("Failed to load channels:", error);
      toast.error("Erro ao carregar canais");
    } finally {
      setLoading(false);
    }
  };

  const handleFlowChange = async (channelId: string, flowId: string) => {
    try {
      await api.admin.setChannelActiveFlow(channelId, { flow_id: flowId });
      
      // Update local state to reflect the change
      setChannels(prevChannels =>
        prevChannels.map(channel => {
          if (channel.id === channelId) {
            return {
              ...channel,
              flows: channel.flows.map(flow => ({
                ...flow,
                is_active: flow.id === flowId
              }))
            };
          }
          return channel;
        })
      );
    } catch (error) {
      console.error("Failed to update active flow:", error);
      throw error; // Let the component handle the error
    }
  };

  useEffect(() => {
    loadChannels();
  }, []);

  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-6xl px-4 py-6 md:py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-lg bg-emerald-100 dark:bg-emerald-900 ring-1 ring-emerald-200 dark:ring-emerald-800 grid place-items-center">
              <Smartphone className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
            </div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Canais</h1>
          </div>
          <p className="text-muted-foreground">
            Gerencie seus canais do WhatsApp e configure qual fluxo está ativo para cada número.
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900">
                <Smartphone className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">
                  {loading ? "—" : channels.length}
                </p>
                <p className="text-xs text-muted-foreground">Total de Canais</p>
              </div>
            </div>
          </Card>
          
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900">
                <Bot className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">
                  {loading ? "—" : channels.filter(ch => ch.flows.some(f => f.is_active)).length}
                </p>
                <p className="text-xs text-muted-foreground">Com Fluxo Ativo</p>
              </div>
            </div>
          </Card>
          
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900">
                <Settings className="w-4 h-4 text-purple-600 dark:text-purple-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                  {loading ? "—" : channels.reduce((total, ch) => total + ch.flows.length, 0)}
                </p>
                <p className="text-xs text-muted-foreground">Total de Fluxos</p>
              </div>
            </div>
          </Card>
        </div>

        {/* Channels List */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-2 border-emerald-200 border-t-emerald-600 rounded-full animate-spin" />
          </div>
        ) : channels.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {channels.map(channel => (
              <ChannelCard 
                key={channel.id} 
                channel={channel} 
                onFlowChange={handleFlowChange}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-emerald-100 dark:bg-emerald-900 flex items-center justify-center">
              <Smartphone className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
            </div>
            <h3 className="text-lg font-semibold mb-2">Nenhum canal configurado</h3>
            <p className="text-muted-foreground mb-6 max-w-md mx-auto">
              Você precisa configurar pelo menos um canal do WhatsApp para começar a usar os fluxos automatizados.
            </p>
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Para adicionar um canal, você pode usar a API administrativa ou entrar em contato com suporte.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

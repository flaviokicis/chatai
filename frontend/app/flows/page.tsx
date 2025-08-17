"use client";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { PageHeader } from "@/components/ui/page-header";
import { cn } from "@/lib/utils";
import Link from "next/link";
import {
  Bot,
  MessageSquareMore,
  Smartphone,
  Instagram,
  Globe,
  Settings,
  Plus,
  Clock,
  Loader2,
} from "lucide-react";
import { useFlows, useChannels } from "@/lib/hooks/use-api";
import { useState } from "react";

function ChannelBadge({ channel }: { channel: string }) {
  const getChannelIcon = () => {
    switch (channel.toLowerCase()) {
      case 'whatsapp':
        return <Smartphone className="h-3 w-3 mr-1" />;
      case 'instagram':
        return <Instagram className="h-3 w-3 mr-1" />;
      default:
        return <MessageSquareMore className="h-3 w-3 mr-1" />;
    }
  };

  return (
    <Badge variant="secondary" className="gap-1">
      {getChannelIcon()}
      {channel}
    </Badge>
  );
}

function getChannelIcon(channelType: string) {
  switch (channelType.toLowerCase()) {
    case 'whatsapp':
      return Smartphone;
    case 'instagram':
      return Instagram;
    default:
      return MessageSquareMore;
  }
}

function getStepsCount(definition?: any): number {
  if (!definition || !definition.nodes) return 0;
  return definition.nodes.length || 0;
}

function getAgentNames(definition?: any): string[] {
  // For now, return a default agent name
  // In the future, this could be extracted from the flow definition
  return ["AI Agent"];
}

export default function FlowsPage() {
  const { data: flows, isLoading: flowsLoading, isError: flowsError } = useFlows();
  const { data: channels, isLoading: channelsLoading } = useChannels();
  const [enabledFlows, setEnabledFlows] = useState<Record<number, boolean>>({});

  // Create a map of channel instances for quick lookup
  const channelMap = channels?.reduce((acc, channel) => {
    acc[channel.id] = channel;
    return acc;
  }, {} as Record<number, any>) || {};
  const isLoading = flowsLoading || channelsLoading;

  if (isLoading) {
    return (
      <div className="min-h-screen w-full bg-background">
        <div className="mx-auto max-w-6xl px-4 py-6 md:py-8">
          <PageHeader
            title="Fluxos"
            description="Crie e gerencie seus fluxos por canal. Cada fluxo pode ter seus próprios agentes e configurações."
            icon={Bot}
          />
          <div className="flex justify-center items-center min-h-48">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        </div>
      </div>
    );
  }

  if (flowsError) {
    return (
      <div className="min-h-screen w-full bg-background">
        <div className="mx-auto max-w-6xl px-4 py-6 md:py-8">
          <PageHeader
            title="Fluxos"
            description="Crie e gerencie seus fluxos por canal. Cada fluxo pode ter seus próprios agentes e configurações."
            icon={Bot}
          />
          <Card>
            <CardContent className="p-6">
              <p className="text-red-600">Erro ao carregar fluxos. Tente novamente.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-6xl px-4 py-6 md:py-8">
        <div className="mb-6">
          <PageHeader
            title="Fluxos"
            description="Crie e gerencie seus fluxos por canal. Cada fluxo pode ter seus próprios agentes e configurações."
            icon={Bot}
          />
          <div className="flex justify-end -mt-4">
            <Link href="/flows/new" className={cn(buttonVariants(), "gap-2")}> 
              <Plus className="h-4 w-4" />
              Criar fluxo
            </Link>
          </div>
        </div>

        {!flows || flows.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Bot className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">Nenhum fluxo criado ainda</h3>
              <p className="text-muted-foreground text-center mb-4 max-w-md">
                Crie seu primeiro fluxo de conversação para começar a automatizar suas interações com clientes.
              </p>
              <Link href="/flows/new" className={cn(buttonVariants(), "gap-2")}>
                <Plus className="h-4 w-4" />
                Criar primeiro fluxo
              </Link>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
            {flows.map((flow) => {
              const channel = channelMap[flow.channel_instance_id];
              const Icon = getChannelIcon(channel?.channel_type || 'whatsapp');
              const stepsCount = getStepsCount(flow.definition);
              const agentNames = getAgentNames(flow.definition);
              const isEnabled = enabledFlows[flow.id] ?? true;

              return (
                <Card key={flow.id} className="relative">
                  <CardHeader className="pb-4">
                    <div className="flex items-start justify-between">
                      <Link href={`/flows/${flow.id}`} className="flex items-center gap-3 group">
                        <div className="h-10 w-10 rounded-lg grid place-items-center bg-primary/10 ring-1 ring-primary/20">
                          <Icon className="h-5 w-5 text-primary" />
                        </div>
                        <div className="flex-1">
                          <CardTitle className="text-base group-hover:underline">{flow.name}</CardTitle>
                          <div className="mt-1 flex items-center gap-2">
                            <ChannelBadge channel={channel?.channel_type || 'WhatsApp'} />
                          </div>
                        </div>
                      </Link>
                      <Switch 
                        checked={isEnabled}
                        onCheckedChange={(checked) => {
                          setEnabledFlows(prev => ({ ...prev, [flow.id]: checked }));
                          // TODO: Implement API call to update flow status
                        }}
                      />
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      Fluxo ID: {flow.flow_id}
                    </p>

                    <div className="grid grid-cols-2 gap-4 pt-2 border-t">
                      <div className="text-center">
                        <div className="text-lg font-semibold">{stepsCount}</div>
                        <div className="text-xs text-muted-foreground">Etapas</div>
                      </div>
                      <div className="text-center">
                        <div className="text-sm font-medium">{agentNames.join(", ")}</div>
                        <div className="text-xs text-muted-foreground">Agentes</div>
                      </div>
                    </div>

                    <div className="flex gap-2 pt-2">
                      <Link
                        href={`/flows/${flow.id}`}
                        className={cn(buttonVariants({ variant: "outline", size: "sm" }), "flex-1")}
                      >
                        <Settings className="h-3.5 w-3.5 mr-1.5" />
                        Configurar
                      </Link>
                      <Button variant="outline" size="sm" className="flex-1">
                        <Clock className="h-3.5 w-3.5 mr-1.5" />
                        Histórico
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}



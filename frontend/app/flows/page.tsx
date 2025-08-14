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
} from "lucide-react";

const flows = [
  {
    id: "sales-whatsapp",
    name: "Qualificação de Vendas (WhatsApp)",
    channel: "WhatsApp",
    icon: Smartphone,
    description: "Coleta informações de lead e direciona o atendimento.",
    status: "active",
    steps: 12,
    agents: ["Sales Qualifier"],
    enabled: true,
  },
  {
    id: "support-instagram",
    name: "Atendimento Inicial (Instagram)",
    channel: "Instagram",
    icon: Instagram,
    description: "Primeira triagem e roteamento de dúvidas comuns.",
    status: "active",
    steps: 9,
    agents: ["AI Receptionist"],
    enabled: true,
  },
];

function ChannelBadge({ channel }: { channel: string }) {
  return <Badge variant="secondary">{channel}</Badge>;
}

export default function FlowsPage() {
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

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
          {flows.map((flow) => {
            const Icon = flow.icon;
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
                          <ChannelBadge channel={flow.channel} />
                        </div>
                      </div>
                    </Link>
                    <Switch checked={flow.enabled} />
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground leading-relaxed">{flow.description}</p>

                  <div className="grid grid-cols-2 gap-4 pt-2 border-t">
                    <div className="text-center">
                      <div className="text-lg font-semibold">{flow.steps}</div>
                      <div className="text-xs text-muted-foreground">Etapas</div>
                    </div>
                    <div className="text-center">
                      <div className="text-sm font-medium">{flow.agents.join(", ")}</div>
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
      </div>
    </div>
  );
}



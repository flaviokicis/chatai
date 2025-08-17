"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/ui/page-header";
import { Plus, Save, ArrowLeft, Loader2, Smartphone, Instagram, MessageSquareMore } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { useChannels, useCreateFlow, useExampleFlow } from "@/lib/hooks/use-api";
import Link from "next/link";

export default function NewFlowPage() {
  const router = useRouter();
  const { data: channels, isLoading: channelsLoading } = useChannels();
  const { data: exampleFlow } = useExampleFlow();
  const createFlow = useCreateFlow();

  const [formData, setFormData] = useState({
    name: "",
    flow_id: "",
    channel_instance_id: "",
    definition: {} as any,
  });

  const [useExampleTemplate, setUseExampleTemplate] = useState(true);

  useEffect(() => {
    if (exampleFlow && useExampleTemplate) {
      setFormData(prev => ({
        ...prev,
        definition: exampleFlow,
      }));
    }
  }, [exampleFlow, useExampleTemplate]);

  // Generate flow_id from name
  useEffect(() => {
    if (formData.name) {
      const flowId = formData.name
        .toLowerCase()
        .replace(/[^\w\s-]/g, '') // Remove special characters except hyphens
        .replace(/\s+/g, '_') // Replace spaces with underscores
        .replace(/-+/g, '_'); // Replace hyphens with underscores
      
      setFormData(prev => ({
        ...prev,
        flow_id: flowId,
      }));
    }
  }, [formData.name]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.name || !formData.channel_instance_id) {
      alert("Por favor, preencha todos os campos obrigatórios.");
      return;
    }

    const definition = useExampleTemplate && exampleFlow ? exampleFlow : formData.definition;
    
    createFlow.mutate({
      name: formData.name,
      flow_id: formData.flow_id,
      channel_instance_id: Number(formData.channel_instance_id),
      definition,
    }, {
      onSuccess: (flow) => {
        router.push(`/flows/${flow.id}`);
      },
      onError: (error) => {
        console.error("Erro ao criar fluxo:", error);
        alert("Erro ao criar fluxo. Tente novamente.");
      },
    });
  };

  const getChannelIcon = (channelType: string) => {
    switch (channelType.toLowerCase()) {
      case 'whatsapp':
        return <Smartphone className="h-4 w-4" />;
      case 'instagram':
        return <Instagram className="h-4 w-4" />;
      default:
        return <MessageSquareMore className="h-4 w-4" />;
    }
  };

  if (channelsLoading) {
    return (
      <div className="min-h-screen w-full bg-background">
        <div className="mx-auto max-w-4xl px-4 py-6 md:py-8">
          <PageHeader
            title="Criar Novo Fluxo"
            description="Configure um novo fluxo de conversação para automatizar suas interações."
            icon={Plus}
          />
          <div className="flex justify-center items-center min-h-48">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-4xl px-4 py-6 md:py-8">
        <PageHeader
          title="Criar Novo Fluxo"
          description="Configure um novo fluxo de conversação para automatizar suas interações."
          icon={Plus}
        />

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Information */}
          <Card>
            <CardHeader>
              <CardTitle>Informações Básicas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="name" className="text-sm font-medium">
                  Nome do Fluxo *
                </Label>
                <Input
                  id="name"
                  placeholder="Ex: Qualificação de Vendas"
                  value={formData.name}
                  onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                  className="w-full"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Nome descritivo para identificar este fluxo
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="flow_id" className="text-sm font-medium">
                  ID do Fluxo
                </Label>
                <Input
                  id="flow_id"
                  placeholder="qualificacao_de_vendas"
                  value={formData.flow_id}
                  onChange={(e) => setFormData(prev => ({ ...prev, flow_id: e.target.value }))}
                  className="w-full"
                  readOnly
                />
                <p className="text-xs text-muted-foreground">
                  Identificador único gerado automaticamente
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="channel" className="text-sm font-medium">
                  Canal *
                </Label>
                <Select
                  value={formData.channel_instance_id}
                  onValueChange={(value) => setFormData(prev => ({ ...prev, channel_instance_id: value }))}
                  required
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione um canal" />
                  </SelectTrigger>
                  <SelectContent>
                    {channels?.map((channel) => (
                      <SelectItem key={channel.id} value={channel.id.toString()}>
                        <div className="flex items-center gap-2">
                          {getChannelIcon(channel.channel_type)}
                          <span className="capitalize">{channel.channel_type}</span>
                          {channel.phone_number && (
                            <span className="text-muted-foreground">
                              ({channel.phone_number})
                            </span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Escolha em qual canal este fluxo será executado
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Template Selection */}
          <Card>
            <CardHeader>
              <CardTitle>Configuração do Fluxo</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="flex items-center space-x-2">
                  <input
                    type="radio"
                    id="use-example"
                    name="template"
                    checked={useExampleTemplate}
                    onChange={() => setUseExampleTemplate(true)}
                    className="h-4 w-4"
                  />
                  <Label htmlFor="use-example" className="text-sm font-medium cursor-pointer">
                    Usar template de exemplo
                  </Label>
                </div>
                <div className="ml-6 text-sm text-muted-foreground">
                  <p>Começar com um fluxo de exemplo pré-configurado para qualificação de vendas.</p>
                  {exampleFlow && (
                    <p className="mt-1">
                      <strong>Template:</strong> {exampleFlow.id} - {exampleFlow.nodes?.length || 0} nós configurados
                    </p>
                  )}
                </div>

                <div className="flex items-center space-x-2">
                  <input
                    type="radio"
                    id="blank-flow"
                    name="template"
                    checked={!useExampleTemplate}
                    onChange={() => setUseExampleTemplate(false)}
                    className="h-4 w-4"
                  />
                  <Label htmlFor="blank-flow" className="text-sm font-medium cursor-pointer">
                    Começar do zero
                  </Label>
                </div>
                <div className="ml-6 text-sm text-muted-foreground">
                  <p>Criar um fluxo completamente novo e personalizado.</p>
                </div>

                {!useExampleTemplate && (
                  <div className="space-y-2">
                    <Label htmlFor="custom-definition" className="text-sm font-medium">
                      Definição do Fluxo (JSON)
                    </Label>
                    <Textarea
                      id="custom-definition"
                      placeholder={`{
  "schema_version": "v1",
  "id": "custom_flow",
  "entry": "start",
  "nodes": [
    {
      "id": "start",
      "kind": "Question",
      "key": "initial_question",
      "prompt": "Como posso ajudá-lo hoje?"
    }
  ],
  "edges": []
}`}
                      className="min-h-[200px] font-mono text-sm"
                      value={JSON.stringify(formData.definition, null, 2)}
                      onChange={(e) => {
                        try {
                          const definition = JSON.parse(e.target.value);
                          setFormData(prev => ({ ...prev, definition }));
                        } catch {
                          // Invalid JSON, ignore for now
                        }
                      }}
                    />
                    <p className="text-xs text-muted-foreground">
                      Definição JSON do fluxo seguindo o schema v1
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex gap-3">
            <Button 
              type="submit" 
              size="lg" 
              className="gap-2"
              disabled={createFlow.isPending}
            >
              {createFlow.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              {createFlow.isPending ? "Criando..." : "Criar Fluxo"}
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/flows" className="gap-2">
                <ArrowLeft className="h-4 w-4" />
                Voltar
              </Link>
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

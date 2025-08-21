"use client";

import { Button } from "@/components/ui/button";
import { SaveButton } from "@/components/ui/save-button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/ui/page-header";
import { Globe, Users, MessageCircle, FileText, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTenant, useUpdateTenantConfig } from "@/lib/hooks/use-api";
import { useState, useEffect } from "react";
import { toast } from "sonner";

export default function ProjectPage() {
  const router = useRouter();
  const { data: tenant, isLoading, isError } = useTenant();
  const updateTenantConfig = useUpdateTenantConfig();
  
  const [formData, setFormData] = useState({
    project_description: "",
    target_audience: "",
    communication_style: "",
  });

  const [hasChanges, setHasChanges] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (tenant) {
      const newData = {
        project_description: tenant.project_description || "",
        target_audience: tenant.target_audience || "",
        communication_style: tenant.communication_style || "",
      };
      setFormData(newData);
      setHasChanges(false);
    }
  }, [tenant]);

  const handleInputChange = (field: keyof typeof formData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const handleSave = () => {
    updateTenantConfig.mutate(formData, {
      onSuccess: () => {
        setHasChanges(false);
        setSaveSuccess(true);
        toast.success("Configurações salvas com sucesso!", {
          description: "Suas configurações globais foram atualizadas e já estão ativas.",
          duration: 4000,
        });
        // Reset success state after animation
        setTimeout(() => setSaveSuccess(false), 2500);
      },
      onError: (error) => {
        console.error("Erro ao salvar:", error);
        setSaveSuccess(false);
        toast.error("Erro ao salvar configurações", {
          description: "Houve um problema ao salvar suas configurações. Tente novamente.",
          duration: 5000,
        });
      },
    });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen w-full bg-background">
        <div className="mx-auto max-w-4xl px-4 py-6 md:py-8">
          <PageHeader
            title="Configurações Globais"
            description="Estas são as configurações padrão para todos os fluxos. Quando você personalizar um fluxo, as configurações dele terão prioridade sobre as globais."
            icon={Globe}
          />
          <div className="flex justify-center items-center min-h-48">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="min-h-screen w-full bg-background">
        <div className="mx-auto max-w-4xl px-4 py-6 md:py-8">
          <PageHeader
            title="Configurações Globais"
            description="Estas são as configurações padrão para todos os fluxos. Quando você personalizar um fluxo, as configurações dele terão prioridade sobre as globais."
            icon={Globe}
          />
          <Card>
            <CardContent className="p-6">
              <p className="text-red-600">Erro ao carregar configurações. Tente novamente.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-4xl px-4 py-6 md:py-8">
        <PageHeader
          title="Configurações Globais"
          description="Estas são as configurações padrão para todos os fluxos. Quando você personalizar um fluxo, as configurações dele terão prioridade sobre as globais."
          icon={Globe}
        />

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Descrição geral
                <span className="text-xs font-normal text-muted-foreground ml-2">
                  (Opcional) • Ajuda a IA a entender seu contexto de negócio
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="project-description" className="text-sm font-medium">
                  Sobre o que é o seu projeto?
                </Label>
                <Textarea
                  id="project-description"
                  placeholder="Descreva seu negócio, produtos ou serviços em detalhes. Inclua o que você oferece, sua proposta de valor, informações de preços e qualquer detalhe que ajude os clientes a entenderem o que você faz. Isso ajuda nossos agentes de IA a fornecer respostas precisas e relevantes.

Exemplo: Somos um estúdio boutique de fitness oferecendo treinos personalizados, aulas em grupo e consultoria de nutrição. Nossos pacotes variam de R$ 250-1.000/sessão, com planos mensais disponíveis. Somos especializados em força e mobilidade para profissionais com pouco tempo."
                  className="min-h-[120px] resize-none"
                  value={formData.project_description}
                  onChange={(e) => handleInputChange('project_description', e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Seja específico sobre suas ofertas, preços e diferenciais
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Público-alvo
                <span className="text-xs font-normal text-muted-foreground ml-2">
                  (Opcional) • Permite fluxo de conversa personalizado
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="audience-description" className="text-sm font-medium">
                  Quem são seus clientes ideais?
                </Label>
                <Textarea
                  id="audience-description"
                  placeholder="Descreva a demografia do seu público, dores, objetivos e preferências de comunicação. Inclua detalhes sobre perguntas e preocupações comuns e o que procuram ao entrar em contato.

Exemplo: Profissionais ocupados de 25 a 45 anos que valorizam eficiência e resultados. Geralmente perguntam sobre flexibilidade de horários, pacotes e prazos de resultados. Preferem comunicação direta e respostas rápidas. Preocupações comuns incluem falta de tempo e se nossa abordagem se adequa ao nível de condicionamento."
                  className="min-h-[120px] resize-none"
                  value={formData.target_audience}
                  onChange={(e) => handleInputChange('target_audience', e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Ajude nossa IA a entender com quem está falando e o que importa para essas pessoas
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageCircle className="h-5 w-5" />
                Estilo de Comunicação e Voz
                <span className="text-xs font-normal text-muted-foreground ml-2">
                  (Opcional) • A IA aprende a soar como você
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="communication-style" className="text-sm font-medium">
                  Compartilhe exemplos de como você se comunica com clientes
                </Label>
                <Textarea
                  id="communication-style"
                  placeholder="Cole exemplos reais de mensagens, e-mails ou respostas a clientes. Inclua diferentes cenários como dúvidas iniciais, follow-ups, agendamentos e resolução de problemas. Isso ajuda a IA a combinar seu tom, estilo e personalidade.

Exemplos de mensagens:
- 'Oi, Sarah! Obrigado por entrar em contato sobre nossos programas. Vou adorar te ajudar a encontrar o ideal para seus objetivos...'
- 'Tudo bem! Acontece precisar remarcar :) Tenho alguns horários disponíveis esta semana...'
- 'Ótima pergunta sobre nossa consultoria de nutrição. Inclui o seguinte...'

Quanto mais exemplos você fornecer, melhor a IA pode soar como você!"
                  className="min-h-[160px] resize-none"
                  value={formData.communication_style}
                  onChange={(e) => handleInputChange('communication_style', e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Inclua vários cenários: cumprimentos, explicações, resolução de problemas e encerramentos
                </p>
              </div>
            </CardContent>
          </Card>

          <div className="flex gap-3">
            <SaveButton
              size="lg"
              isLoading={updateTenantConfig.isPending}
              isSuccess={saveSuccess}
              hasChanges={hasChanges}
              onSave={handleSave}
            />
            <Button variant="outline" size="lg" onClick={() => router.push('/')}>
              Cancelar
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

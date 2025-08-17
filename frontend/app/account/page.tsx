"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { User, Mail, Save, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTenant } from "@/lib/hooks/use-api";
import { useState, useEffect } from "react";

export default function AccountPage() {
  const router = useRouter();
  const { data: tenant, isLoading, isError } = useTenant();
  
  const [formData, setFormData] = useState({
    first_name: "",
    last_name: "",
    email: "",
  });

  useEffect(() => {
    if (tenant) {
      setFormData({
        first_name: tenant.first_name,
        last_name: tenant.last_name,
        email: tenant.email,
      });
    }
  }, [tenant]);

  if (isLoading) {
    return (
      <div className="min-h-screen w-full bg-background">
        <div className="mx-auto max-w-4xl px-4 py-6 md:py-8">
          <PageHeader
            title="Configurações da Conta"
            description="Gerencie suas informações de conta"
            icon={User}
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
            title="Configurações da Conta"
            description="Gerencie suas informações de conta"
            icon={User}
          />
          <Card>
            <CardContent className="p-6">
              <p className="text-red-600">Erro ao carregar dados da conta. Tente novamente.</p>
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
          title="Configurações da Conta"
          description="Gerencie suas informações de conta"
          icon={User}
        />

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Informações Pessoais
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="first_name" className="text-sm font-medium">
                Nome
              </Label>
              <Input
                id="first_name"
                placeholder="Digite seu nome"
                value={formData.first_name}
                onChange={(e) => setFormData(prev => ({ ...prev, first_name: e.target.value }))}
                className="w-full"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="last_name" className="text-sm font-medium">
                Sobrenome
              </Label>
              <Input
                id="last_name"
                placeholder="Digite seu sobrenome"
                value={formData.last_name}
                onChange={(e) => setFormData(prev => ({ ...prev, last_name: e.target.value }))}
                className="w-full"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-medium flex items-center gap-2">
                <Mail className="h-4 w-4" />
                Endereço de e-mail
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="Digite seu e-mail"
                value={formData.email}
                onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                Usaremos este e-mail para notificações e recuperação de conta
              </p>
            </div>

            <div className="flex gap-3 pt-4">
              <Button 
                className="gap-2"
                onClick={() => {
                  // For now, just show that this feature is not implemented
                  alert("Atualização de informações pessoais será implementada em breve!");
                }}
              >
                <Save className="h-4 w-4" />
                Salvar alterações
              </Button>
              <Button variant="outline" onClick={() => router.push('/')}>
                Cancelar
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

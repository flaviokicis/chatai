"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { User, Mail, Save } from "lucide-react";
import { useRouter } from "next/navigation";

export default function AccountPage() {
  const router = useRouter();

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
              <Label htmlFor="username" className="text-sm font-medium">
                Nome de usuário
              </Label>
              <Input
                id="username"
                placeholder="Digite seu nome de usuário"
                defaultValue="jessica_doe"
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                Este é seu identificador único na plataforma
              </p>
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
                defaultValue="jessica@company.com"
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                Usaremos este e-mail para notificações e recuperação de conta
              </p>
            </div>

            <div className="flex gap-3 pt-4">
              <Button className="gap-2">
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

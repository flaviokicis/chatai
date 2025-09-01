"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2, Phone, Shield, AlertCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api-client";

interface AdminPhoneManagerProps {
  tenantId: string;
  initialAdminPhones?: string[];
  onAdminPhonesChanged?: (phones: string[]) => void;
}

export function AdminPhoneManager({ 
  tenantId, 
  initialAdminPhones = [], 
  onAdminPhonesChanged 
}: AdminPhoneManagerProps) {
  const [adminPhones, setAdminPhones] = useState<string[]>(initialAdminPhones);
  const [newPhone, setNewPhone] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Load admin phones from API
  useEffect(() => {
    const loadAdminPhones = async () => {
      if (!tenantId) return;
      
      setIsLoading(true);
      try {
        const response = await api.admin.getAdminPhones(tenantId);
        setAdminPhones(response.admin_phone_numbers);
      } catch (error) {
        console.error("Failed to load admin phones:", error);
        toast.error("Erro ao carregar números de administradores");
      } finally {
        setIsLoading(false);
      }
    };

    loadAdminPhones();
  }, [tenantId]);

  const validatePhoneNumber = (phone: string): boolean => {
    // Simple validation for Brazilian phone numbers
    const cleanPhone = phone.replace(/\D/g, "");
    return cleanPhone.length >= 10 && cleanPhone.length <= 13;
  };

  const normalizePhoneNumber = (phone: string): string => {
    // Remove all non-digits
    let clean = phone.replace(/\D/g, "");
    
    // Add country code if missing
    if (clean.length === 11 && clean.startsWith("11")) {
      clean = "55" + clean; // Add Brazil country code
    } else if (clean.length === 10) {
      clean = "5511" + clean; // Add Brazil + São Paulo
    }
    
    // Format with + prefix
    return "+" + clean;
  };

  const handleAddPhone = async () => {
    if (!newPhone.trim()) {
      toast.error("Digite um número de telefone");
      return;
    }

    if (!validatePhoneNumber(newPhone)) {
      toast.error("Número de telefone inválido. Use formato: +5511999999999 ou 11999999999");
      return;
    }

    const normalizedPhone = normalizePhoneNumber(newPhone);
    
    if (adminPhones.includes(normalizedPhone)) {
      toast.error("Este número já está na lista de administradores");
      return;
    }

    setIsAdding(true);
    
    try {
      const updatedPhones = [...adminPhones, normalizedPhone];
      
      // Save to backend
      await api.admin.updateAdminPhones(updatedPhones, tenantId);
      
      setAdminPhones(updatedPhones);
      setNewPhone("");
      onAdminPhonesChanged?.(updatedPhones);
      
      toast.success("Número de administrador adicionado!", {
        description: "Este número agora pode editar o fluxo durante conversas"
      });
    } catch (error) {
      console.error("Failed to add admin phone:", error);
      toast.error("Erro ao adicionar número de administrador");
    } finally {
      setIsAdding(false);
    }
  };

  const handleRemovePhone = async (phoneToRemove: string) => {
    try {
      const updatedPhones = adminPhones.filter(phone => phone !== phoneToRemove);
      
      // Save to backend
      await api.admin.updateAdminPhones(updatedPhones, tenantId);
      
      setAdminPhones(updatedPhones);
      onAdminPhonesChanged?.(updatedPhones);
      
      toast.success("Número de administrador removido");
    } catch (error) {
      console.error("Failed to remove admin phone:", error);
      toast.error("Erro ao remover número de administrador");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Edição ao Vivo
        </CardTitle>
        <CardDescription>
          Números de telefone que podem editar este fluxo durante conversas no WhatsApp.
          Administradores podem dar comandos, por exemplo: quando o cliente perguntar se "Temos pronta entrega", responda "Sim, temos pronta entrega". O fluxo será modificado automaticamente.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Carregando números de administradores...
          </div>
        )}
        {/* Info box */}
        <div className="flex items-start gap-3 p-3 bg-blue-50 rounded-lg border border-blue-200">
          <AlertCircle className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-blue-800">
            <p className="font-medium mb-1">Como funciona a edição ao vivo:</p>
            <ul className="space-y-1 text-xs">
              <li>• Durante conversas normais, administradores podem dar instruções</li>
              <li>• Exemplo: "Não responda 'Como posso ajudar', responda 'Qual seu problema?' ou qualquer outro pedido"</li>
              <li>• O fluxo é modificado automaticamente e salvo</li>
              <li>• Use "vamos recomeçar" para reiniciar conversas</li>
            </ul>
          </div>
        </div>

        {/* Current admin phones */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Números de Administradores</h4>
          {adminPhones.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum número de administrador configurado. Adicione um número para habilitar a edição ao vivo.
            </p>
          ) : (
            <div className="space-y-2">
              {adminPhones.map((phone) => (
                <div key={phone} className="flex items-center justify-between p-2 bg-muted rounded-lg">
                  <div className="flex items-center gap-2">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <Badge variant="secondary" className="font-mono">
                      {phone}
                    </Badge>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRemovePhone(phone)}
                    className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Add new phone */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Adicionar Administrador</h4>
          <div className="flex gap-2">
            <Input
              placeholder="Ex: +5511999999999 ou 11999999999"
              value={newPhone}
              onChange={(e) => setNewPhone(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleAddPhone();
                }
              }}
              className="flex-1"
            />
            <Button 
              onClick={handleAddPhone}
              disabled={isAdding || !newPhone.trim()}
              className="gap-2"
            >
              <Plus className="h-4 w-4" />
              Adicionar
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Formatos aceitos: +5511999999999, 5511999999999, 11999999999
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

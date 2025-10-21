"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, User, Sparkles, Check } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

interface PersonalityExample {
  context: string;
  message: string;
}

interface PersonalityPreset {
  id: string;
  name: string;
  description: string;
  examples: PersonalityExample[];
  avatar_url: string;
  recommended_for: string[];
}

interface PersonalitySelectorProps {
  tenantId: string;
  currentPersonalityId?: string;
  onPersonalityChange?: (personalityId: string) => void;
}


export function PersonalitySelector({ 
  tenantId,
  currentPersonalityId,
  onPersonalityChange 
}: PersonalitySelectorProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [personalities, setPersonalities] = useState<PersonalityPreset[]>([]);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  // Load personalities on mount
  useState(() => {
    loadPersonalities();
  });

  const loadPersonalities = async () => {
    try {
      setLoading(true);
      const adminPassword = localStorage.getItem("adminPassword");
      if (!adminPassword) {
        toast.error("Admin authentication required");
        return;
      }

      const response = await fetch("/api/controller/personalities", {
        headers: {
          Authorization: `Bearer ${adminPassword}`,
        },
      });

      if (!response.ok) {
        throw new Error("Failed to load personalities");
      }

      const data = await response.json();
      setPersonalities(data);

      // Set initial index to current personality if exists
      if (currentPersonalityId) {
        const index = data.findIndex((p: PersonalityPreset) => p.id === currentPersonalityId);
        if (index !== -1) {
          setSelectedIndex(index);
        }
      }
    } catch (error) {
      console.error("Failed to load personalities:", error);
      toast.error("Erro ao carregar personalidades");
    } finally {
      setLoading(false);
    }
  };

  const handleApplyPersonality = async () => {
    if (!personalities[selectedIndex]) return;

    const personality = personalities[selectedIndex];
    
    try {
      setApplying(true);
      const adminPassword = localStorage.getItem("adminPassword");
      if (!adminPassword) {
        toast.error("Admin authentication required");
        return;
      }

      const response = await fetch(`/api/controller/tenants/${tenantId}/apply-personality`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${adminPassword}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          personality_id: personality.id,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to apply personality");
      }

      toast.success(`Personalidade "${personality.name}" aplicada com sucesso!`);
      
      if (onPersonalityChange) {
        onPersonalityChange(personality.id);
      }
    } catch (error) {
      console.error("Failed to apply personality:", error);
      toast.error("Erro ao aplicar personalidade");
    } finally {
      setApplying(false);
    }
  };

  const handlePrevious = () => {
    setSelectedIndex((prev) => (prev === 0 ? personalities.length - 1 : prev - 1));
  };

  const handleNext = () => {
    setSelectedIndex((prev) => (prev === personalities.length - 1 ? 0 : prev + 1));
  };

  if (loading) {
    return (
      <Card className="p-8">
        <div className="flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </Card>
    );
  }

  if (personalities.length === 0) {
    return (
      <Card className="p-8">
        <div className="text-center text-muted-foreground">
          Nenhuma personalidade disponível
        </div>
      </Card>
    );
  }

  const currentPersonality = personalities[selectedIndex];

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-yellow-500" />
            Personalidade do Atendimento
          </CardTitle>
          {currentPersonalityId === currentPersonality?.id && (
            <Badge variant="secondary" className="bg-green-100 dark:bg-green-900">
              <Check className="w-3 h-3 mr-1" />
              Atual
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Personality Carousel */}
        <div className="relative flex items-center justify-between">
          <Button
            variant="ghost"
            size="icon"
            onClick={handlePrevious}
            className="absolute left-0 z-10"
          >
            <ChevronLeft className="w-5 h-5" />
          </Button>

          <div className="flex-1 flex flex-col items-center gap-4 px-12">
            {/* Avatar Image */}
            <div className="w-24 h-24 rounded-full overflow-hidden bg-muted/20">
              <img 
                src={currentPersonality.avatar_url} 
                alt={currentPersonality.name}
                className="w-full h-full object-cover"
                onError={(e) => {
                  // Fallback to placeholder if image fails to load
                  e.currentTarget.style.display = 'none';
                  e.currentTarget.parentElement?.appendChild(
                    Object.assign(document.createElement('div'), {
                      className: 'w-full h-full flex items-center justify-center text-3xl',
                      innerHTML: {
                        warm_empathetic: '❤️',
                        concise_direct: '⚡',
                        formal_polite: '🎓',
                        consultative_didactic: '💡',
                        energetic_promotional: '✨',
                        calm_reassuring: '🌿'
                      }[currentPersonality.id] || '👤'
                    })
                  );
                }}
              />
            </div>
            
            <div className="text-center space-y-2">
              <h3 className="font-semibold text-lg">{currentPersonality.name}</h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                {currentPersonality.description}
              </p>
            </div>

            {/* Recommended for badges */}
            <div className="flex flex-wrap gap-1 justify-center max-w-sm">
              {currentPersonality.recommended_for.map((rec) => (
                <Badge key={rec} variant="outline" className="text-xs">
                  {rec}
                </Badge>
              ))}
            </div>
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={handleNext}
            className="absolute right-0 z-10"
          >
            <ChevronRight className="w-5 h-5" />
          </Button>
        </div>

        {/* Example Messages */}
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground">Exemplos de Mensagens:</h4>
          <div className="space-y-2">
            {currentPersonality.examples.map((example, idx) => (
              <div key={idx} className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground capitalize">
                  {example.context === "greeting" ? "Saudação" :
                   example.context === "question" ? "Pergunta" :
                   example.context === "closing" ? "Despedida" : example.context}:
                </div>
                <div className="p-3 rounded-lg bg-muted/50 text-sm italic">
                  "{example.message}"
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Pagination dots */}
        <div className="flex justify-center gap-1.5">
          {personalities.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setSelectedIndex(idx)}
              className={`w-2 h-2 rounded-full transition-all ${
                idx === selectedIndex
                  ? "bg-primary w-6"
                  : "bg-muted-foreground/30 hover:bg-muted-foreground/50"
              }`}
            />
          ))}
        </div>

        {/* Apply Button */}
        <Button
          onClick={handleApplyPersonality}
          disabled={applying || currentPersonalityId === currentPersonality?.id}
          className="w-full"
        >
          {applying ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
              Aplicando...
            </>
          ) : currentPersonalityId === currentPersonality?.id ? (
            <>
              <Check className="w-4 h-4 mr-2" />
              Personalidade Atual
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4 mr-2" />
              Aplicar Esta Personalidade
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}

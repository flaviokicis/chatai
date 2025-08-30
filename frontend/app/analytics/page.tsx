"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/ui/page-header";
import { 
  BarChart3, 
  TrendingUp, 
  TrendingDown, 
  Users, 
  Zap, 
  Target, 
  DollarSign,
  Clock,
  MapPin,
  Lightbulb,
  Building,
  Home,
  Factory,
  MessageCircle,
  CheckCircle2,
  XCircle,
  RefreshCw
} from "lucide-react";

// Mock data for LED lighting business
const mockData = {
  overview: {
    totalLeads: 347,
    qualifiedLeads: 89,
    conversionRate: 25.6,
    avgDealSize: 2850,
    monthlyRevenue: 253900,
    growthRate: 18.5
  },
  
  leadFunnel: [
    { stage: "Inquiries", count: 347, color: "bg-blue-500" },
    { stage: "Initial Contact", count: 298, color: "bg-green-500" },
    { stage: "Qualified", count: 89, color: "bg-brand-500" },
    { stage: "Proposal Sent", count: 67, color: "bg-orange-500" },
    { stage: "Closed Won", count: 23, color: "bg-emerald-600" }
  ],
  
  productInterest: [
    { category: "Residential LEDs", percentage: 35, count: 121, color: "from-blue-400 to-blue-600" },
    { category: "Commercial LEDs", percentage: 28, count: 97, color: "from-brand-400 to-brand-600" },
    { category: "Industrial LEDs", percentage: 22, count: 76, color: "from-amber-400 to-amber-600" },
    { category: "Smart Lighting", percentage: 15, count: 53, color: "from-purple-400 to-purple-600" }
  ],
  
  customerSegments: [
    { segment: "Homeowners", count: 145, percentage: 42, icon: Home },
    { segment: "Small Business", count: 98, percentage: 28, icon: Building },
    { segment: "Contractors", count: 67, percentage: 19, icon: Users },
    { segment: "Enterprise", count: 37, percentage: 11, icon: Factory }
  ],
  
  performance: {
    avgResponseTime: "2.3 min",
    qualificationAccuracy: 87,
    customerSatisfaction: 4.8,
    agentEfficiency: 94
  },
  
  peakHours: [
    { hour: "9h", inquiries: 23 },
    { hour: "10h", inquiries: 35 },
    { hour: "11h", inquiries: 42 },
    { hour: "14h", inquiries: 38 },
    { hour: "15h", inquiries: 31 },
    { hour: "16h", inquiries: 28 }
  ],
  
  commonQuestions: [
    { question: "Preço de fita LED", count: 89 },
    { question: "Instalação comercial", count: 67 },
    { question: "LED para casa", count: 45 },
    { question: "Garantia produtos", count: 34 },
    { question: "Consumo energia", count: 28 }
  ]
};

// Progress bar component
function ProgressBar({ value, max, className = "" }: { value: number; max: number; className?: string }) {
  const percentage = (value / max) * 100;
  return (
    <div className={`w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 ${className}`}>
      <div 
        className="bg-gradient-to-r from-brand-400 to-brand-600 h-2 rounded-full transition-all duration-500" 
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

// Funnel stage component
function FunnelStage({ stage, isLast }: { stage: any; isLast: boolean }) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-foreground">{stage.stage}</h4>
          <Badge variant="secondary" className="font-mono">{stage.count}</Badge>
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
          <div 
            className={`${stage.color} h-3 rounded-full transition-all duration-500`}
            style={{ width: `${(stage.count / mockData.leadFunnel[0].count) * 100}%` }}
          />
        </div>
      </div>
      {!isLast && (
        <div className="text-muted-foreground">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </div>
      )}
    </div>
  );
}

export default function AnalyticsPage() {
  const [timeRange, setTimeRange] = useState("30d");
  const [loading, setLoading] = useState(false);

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => setLoading(false), 1500);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto p-6">
      <PageHeader
        title="Analytics & Insights"
        subtitle="Análise completa do desempenho de vendas de LED"
        actions={
          <div className="flex items-center gap-3">
            <Select value={timeRange} onValueChange={setTimeRange}>
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7d">Últimos 7 dias</SelectItem>
                <SelectItem value="30d">Últimos 30 dias</SelectItem>
                <SelectItem value="90d">Últimos 90 dias</SelectItem>
              </SelectContent>
            </Select>
            <Button 
              onClick={handleRefresh} 
              disabled={loading}
              variant="outline"
              size="sm"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        }
      />

      {/* Overview KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <Card className="lg:col-span-2">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold text-foreground">{mockData.overview.totalLeads}</p>
                <p className="text-sm text-muted-foreground">Total de Leads</p>
              </div>
              <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
                <Users className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
            </div>
            <div className="mt-3 flex items-center text-sm">
              <TrendingUp className="w-4 h-4 text-green-500 mr-1" />
              <span className="text-green-600">+{mockData.overview.growthRate}%</span>
              <span className="text-muted-foreground ml-1">vs mês anterior</span>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold text-brand-700">{mockData.overview.qualifiedLeads}</p>
                <p className="text-sm text-muted-foreground">Leads Qualificados</p>
              </div>
              <div className="p-3 rounded-lg bg-brand-100 dark:bg-brand-900">
                <Target className="w-6 h-6 text-brand-600 dark:text-brand-400" />
              </div>
            </div>
            <div className="mt-3 flex items-center text-sm">
              <span className="text-brand-600 font-semibold">{mockData.overview.conversionRate}%</span>
              <span className="text-muted-foreground ml-1">taxa de qualificação</span>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold text-emerald-700">R$ {(mockData.overview.monthlyRevenue / 1000).toFixed(0)}k</p>
                <p className="text-sm text-muted-foreground">Receita Mensal</p>
              </div>
              <div className="p-3 rounded-lg bg-emerald-100 dark:bg-emerald-900">
                <DollarSign className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
              </div>
            </div>
            <div className="mt-3 flex items-center text-sm">
              <span className="text-emerald-600 font-semibold">R$ {mockData.overview.avgDealSize}</span>
              <span className="text-muted-foreground ml-1">ticket médio</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Lead Qualification Funnel */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-brand-600" />
              Funil de Qualificação
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {mockData.leadFunnel.map((stage, index) => (
              <FunnelStage 
                key={stage.stage} 
                stage={stage} 
                isLast={index === mockData.leadFunnel.length - 1} 
              />
            ))}
          </CardContent>
        </Card>

        {/* Performance Metrics */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-amber-600" />
              Performance do Agente
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Tempo de Resposta</span>
                <span className="font-semibold">{mockData.performance.avgResponseTime}</span>
              </div>
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-green-500" />
                <Badge variant="secondary" className="bg-green-100 text-green-700">Excelente</Badge>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Precisão Qualificação</span>
                <span className="font-semibold">{mockData.performance.qualificationAccuracy}%</span>
              </div>
              <ProgressBar value={mockData.performance.qualificationAccuracy} max={100} />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Satisfação Cliente</span>
                <span className="font-semibold">{mockData.performance.customerSatisfaction}/5</span>
              </div>
              <ProgressBar value={mockData.performance.customerSatisfaction * 20} max={100} />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Eficiência Agente</span>
                <span className="font-semibold">{mockData.performance.agentEfficiency}%</span>
              </div>
              <ProgressBar value={mockData.performance.agentEfficiency} max={100} />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Product Interest Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-yellow-600" />
              Interesse por Produtos LED
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {mockData.productInterest.map((product) => (
              <div key={product.category} className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="font-medium">{product.category}</span>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{product.count} leads</Badge>
                    <span className="text-sm font-semibold">{product.percentage}%</span>
                  </div>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                  <div 
                    className={`bg-gradient-to-r ${product.color} h-3 rounded-full transition-all duration-500`}
                    style={{ width: `${product.percentage}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Customer Segments */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="w-5 h-5 text-purple-600" />
              Segmentos de Cliente
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {mockData.customerSegments.map((segment) => {
              const Icon = segment.icon;
              return (
                <div key={segment.segment} className="flex items-center justify-between p-3 rounded-xl bg-muted/50">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-background">
                      <Icon className="w-4 h-4 text-muted-foreground" />
                    </div>
                    <div>
                      <h4 className="font-medium">{segment.segment}</h4>
                      <p className="text-sm text-muted-foreground">{segment.count} clientes</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-brand-600">{segment.percentage}%</p>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>

      {/* Peak Hours and Common Questions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-blue-600" />
              Horários de Pico
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {mockData.peakHours.map((hour, index) => (
                <div key={hour.hour} className="flex items-center gap-4">
                  <span className="text-sm font-medium w-8">{hour.hour}</span>
                  <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                    <div 
                      className="bg-gradient-to-r from-blue-400 to-blue-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${(hour.inquiries / 45) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm text-muted-foreground w-8">{hour.inquiries}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageCircle className="w-5 h-5 text-green-600" />
              Perguntas Mais Frequentes
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {mockData.commonQuestions.map((item, index) => (
                <div key={item.question} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <span className="font-medium">{item.question}</span>
                  <Badge variant="secondary">{item.count}x</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* AI Agent Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-green-600" />
            Status do Agente de Qualificação
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="flex items-center gap-4 p-4 rounded-xl bg-green-50 dark:bg-green-950">
              <div className="p-3 rounded-full bg-green-100 dark:bg-green-900">
                <CheckCircle2 className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <h3 className="font-semibold text-green-800 dark:text-green-200">Online & Ativo</h3>
                <p className="text-sm text-green-600 dark:text-green-400">Processando leads 24/7</p>
              </div>
            </div>
            
            <div className="flex items-center gap-4 p-4 rounded-xl bg-blue-50 dark:bg-blue-950">
              <div className="p-3 rounded-full bg-blue-100 dark:bg-blue-900">
                <BarChart3 className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <h3 className="font-semibold text-blue-800 dark:text-blue-200">Alta Performance</h3>
                <p className="text-sm text-blue-600 dark:text-blue-400">94% de eficiência</p>
              </div>
            </div>
            
            <div className="flex items-center gap-4 p-4 rounded-xl bg-amber-50 dark:bg-amber-950">
              <div className="p-3 rounded-full bg-amber-100 dark:bg-amber-900">
                <Zap className="w-6 h-6 text-amber-600" />
              </div>
              <div>
                <h3 className="font-semibold text-amber-800 dark:text-amber-200">Resposta Rápida</h3>
                <p className="text-sm text-amber-600 dark:text-amber-400">Média 2.3 minutos</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

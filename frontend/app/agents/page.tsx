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
  Calendar, 
  Headphones, 
  Receipt, 
  Users, 
  MessageSquareMore,
  ShoppingCart,
  Phone,
  FileText,
  Clock,
  Settings,
  Plus
} from "lucide-react";

const agents = [
  {
    id: "sales-qualifier",
    name: "Sales Qualifier",
    icon: MessageSquareMore,
    description: "Qualifies leads through intelligent questioning and conversation flow",
    status: "active",
    conversations: 47,
    conversionRate: "23%",
    enabled: true,
  },
  {
    id: "appointment-scheduler",
    name: "Appointment Scheduler", 
    icon: Calendar,
    description: "Handles booking, rescheduling, and calendar management automatically",
    status: "active",
    conversations: 31,
    conversionRate: "89%",
    enabled: true,
  },
  {
    id: "receptionist",
    name: "AI Receptionist",
    icon: Headphones,
    description: "Provides first-line support and routes inquiries to appropriate channels",
    status: "active", 
    conversations: 128,
    conversionRate: "76%",
    enabled: true,
  },
  {
    id: "receipt-processor",
    name: "Receipt Processor",
    icon: Receipt,
    description: "Processes payment confirmations, invoices, and financial documents",
    status: "inactive",
    conversations: 0,
    conversionRate: "—",
    enabled: false,
  },
  {
    id: "queue-manager",
    name: "Queue Manager",
    icon: Users,
    description: "Manages customer queues and wait times during high-volume periods",
    status: "monitoring",
    conversations: 15,
    conversionRate: "94%",
    enabled: true,
  },
  {
    id: "order-assistant",
    name: "Order Assistant",
    icon: ShoppingCart,
    description: "Handles product inquiries, order placement, and purchase assistance",
    status: "inactive",
    conversations: 0,
    conversionRate: "—",
    enabled: false,
  },
  {
    id: "support-specialist",
    name: "Support Specialist",
    icon: Phone,
    description: "Provides technical support and troubleshooting for complex issues",
    status: "inactive",
    conversations: 0,
    conversionRate: "—",
    enabled: false,
  },
  {
    id: "content-curator",
    name: "Content Curator",
    icon: FileText,
    description: "Shares relevant content, resources, and educational materials",
    status: "inactive",
    conversations: 0,
    conversionRate: "—",
    enabled: false,
  },
];

const getStatusBadge = (status: string) => {
  switch (status) {
    case "active":
      return <Badge variant="success">Active</Badge>;
    case "monitoring":
      return <Badge variant="warning">Monitoring</Badge>;
    case "inactive":
      return <Badge variant="outline">Inactive</Badge>;
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
};

export default function AgentsPage() {
  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-6xl px-4 py-6 md:py-8">
        <div className="mb-6">
          <PageHeader
            title="AI Agents"
            description="Manage your automated conversation handlers"
            icon={Bot}
          />
          <div className="flex justify-end -mt-4">
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              Create Agent
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
          {agents.map((agent) => {
            const IconComponent = agent.icon;
            return (
              <Card key={agent.id} className="relative">
                <CardHeader className="pb-4">
                  <div className="flex items-start justify-between">
                    <Link href={`/agents/${agent.id}`} className="flex items-center gap-3 group">
                      <div className={`h-10 w-10 rounded-lg grid place-items-center ${
                        agent.enabled 
                          ? "bg-primary/10 ring-1 ring-primary/20" 
                          : "bg-muted"
                      }`}>
                        <IconComponent className={`h-5 w-5 ${
                          agent.enabled ? "text-primary" : "text-muted-foreground"
                        }`} />
                      </div>
                      <div className="flex-1">
                        <CardTitle className="text-base group-hover:underline">{agent.name}</CardTitle>
                        <div className="mt-1">
                          {getStatusBadge(agent.status)}
                        </div>
                      </div>
                    </Link>
                    <Switch checked={agent.enabled} />
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {agent.description}
                  </p>
                  
                  {agent.enabled && (
                    <div className="grid grid-cols-2 gap-4 pt-2 border-t">
                      <div className="text-center">
                        <div className="text-lg font-semibold">{agent.conversations}</div>
                        <div className="text-xs text-muted-foreground">Conversations</div>
                      </div>
                      <div className="text-center">
                        <div className="text-lg font-semibold text-primary">{agent.conversionRate}</div>
                        <div className="text-xs text-muted-foreground">Success Rate</div>
                      </div>
                    </div>
                  )}

                  <div className="flex gap-2 pt-2">
                    <Link
                      href={`/agents/${agent.id}`}
                      className={cn(
                        buttonVariants({ variant: "outline", size: "sm" }),
                        "flex-1"
                      )}
                    >
                      <Settings className="h-3.5 w-3.5 mr-1.5" />
                      Configure
                    </Link>
                    <Button variant="outline" size="sm" className="flex-1">
                      <Clock className="h-3.5 w-3.5 mr-1.5" />
                      History
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Agent Performance Overview</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="text-center p-4 rounded-lg bg-primary/5">
                <div className="text-2xl font-bold text-primary">221</div>
                <div className="text-sm text-muted-foreground">Total Conversations</div>
              </div>
              <div className="text-center p-4 rounded-lg bg-emerald-50">
                <div className="text-2xl font-bold text-emerald-600">67%</div>
                <div className="text-sm text-muted-foreground">Avg Success Rate</div>
              </div>
              <div className="text-center p-4 rounded-lg bg-blue-50">
                <div className="text-2xl font-bold text-blue-600">4</div>
                <div className="text-sm text-muted-foreground">Active Agents</div>
              </div>
              <div className="text-center p-4 rounded-lg bg-amber-50">
                <div className="text-2xl font-bold text-amber-600">2.3s</div>
                <div className="text-sm text-muted-foreground">Avg Response Time</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

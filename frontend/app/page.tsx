"use client";

import { Bot, Settings, User, FolderOpen } from "lucide-react";
import { Card } from "@/components/ui/card";
import Link from "next/link";

const shortcuts = [
  { href: "/project", icon: FolderOpen, label: "Project", description: "Configure your AI training" },
  { href: "/agents", icon: Bot, label: "Agents", description: "Manage conversation handlers" },
  { href: "/settings", icon: Settings, label: "Settings", description: "App preferences & config" },
  { href: "/account", icon: User, label: "Account", description: "Personal information" },
];

export default function Home() {
  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-4xl px-4 py-6 md:py-8">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-lg bg-primary/10 ring-1 ring-primary/20 grid place-items-center">
              <Bot className="h-6 w-6 text-primary" />
            </div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Inboxed</h1>
          </div>
          <p className="text-muted-foreground">AI agents for WhatsApp inbox automation</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {shortcuts.map((shortcut) => {
            const Icon = shortcut.icon;
            return (
              <Link key={shortcut.href} href={shortcut.href} className="group">
                <Card className="p-6 hover:shadow-md transition-all duration-200 group-hover:border-primary/20">
                  <div className="flex items-center gap-4">
                    <div className="h-12 w-12 rounded-xl bg-primary/10 ring-1 ring-primary/20 grid place-items-center group-hover:bg-primary/15 transition-colors">
                      <Icon className="h-7 w-7 text-primary" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold group-hover:text-primary transition-colors">
                        {shortcut.label}
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        {shortcut.description}
                      </p>
                    </div>
                  </div>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

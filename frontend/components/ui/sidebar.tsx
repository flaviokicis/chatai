"use client";

import { useState, useEffect } from "react";
import { Bot, Home, User, Globe, Settings, MessageCircle, BarChart3 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const sidebarItems = [
  { href: "/", icon: Home, label: "Início" },
  { href: "/analytics", icon: BarChart3, label: "Analytics" },
  { href: "/chats", icon: MessageCircle, label: "Conversas" },
  { href: "/flows", icon: Bot, label: "Fluxos" },
  { href: "/account", icon: User, label: "Conta" },
  { href: "/project", icon: Globe, label: "Configurações Globais" },
  { href: "/settings", icon: Settings, label: "Configurações" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="fixed left-0 top-0 h-full w-16 bg-card border-r border-border flex flex-col items-center justify-center z-50">
      <div className="space-y-3">
        {sidebarItems.map((item) => {
          const Icon = item.icon;
          const isActive = mounted && (
            pathname === item.href || 
            (item.href === "/chats" && pathname?.startsWith("/chats")) ||
            (item.href === "/analytics" && pathname?.startsWith("/analytics")) ||
            (item.href === "/flows" && pathname?.startsWith("/flows"))
          );
          
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center justify-center w-12 h-12 rounded-lg transition-all duration-200 group relative",
                isActive 
                  ? "bg-primary text-primary-foreground shadow-sm scale-100" 
                  : "hover:bg-primary/10 text-muted-foreground hover:text-primary hover:scale-105"
              )}
              title={item.label}
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              
              {/* Tooltip */}
              <div className="absolute left-full ml-3 px-2 py-1 bg-popover text-popover-foreground text-xs rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap border">
                {item.label}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

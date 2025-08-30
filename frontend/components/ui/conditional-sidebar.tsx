"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "./sidebar";

interface ConditionalSidebarProps {
  children: React.ReactNode;
}

export function ConditionalSidebar({ children }: ConditionalSidebarProps) {
  const pathname = usePathname();
  
  // Hide sidebar for controller (admin) pages
  const isControllerPage = pathname.startsWith("/controller");
  
  if (isControllerPage) {
    // Full screen layout for controller pages
    return <main className="min-h-screen">{children}</main>;
  }
  
  // Normal layout with sidebar
  return (
    <>
      <Sidebar />
      <main className="ml-16 min-h-screen">{children}</main>
    </>
  );
}

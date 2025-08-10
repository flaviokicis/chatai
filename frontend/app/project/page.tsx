"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/ui/page-header";
import { FolderOpen, Users, MessageCircle, Save, FileText } from "lucide-react";
import { useRouter } from "next/navigation";

export default function ProjectPage() {
  const router = useRouter();

  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-4xl px-4 py-6 md:py-8">
        <PageHeader
          title="Project Configuration"
          description="Set up your project details for AI agent training"
          icon={FolderOpen}
        />

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Project Description
                <span className="text-xs font-normal text-muted-foreground ml-2">
                  (Optional) • Helps AI understand your business context
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="project-description" className="text-sm font-medium">
                  What is your project about?
                </Label>
                <Textarea
                  id="project-description"
                  placeholder="Describe your business, products, or services in detail. Include what you offer, your value proposition, pricing information, and any key details that help customers understand what you do. This helps our AI agents provide accurate and relevant responses to inquiries.

Example: We're a boutique fitness studio offering personalized training sessions, group classes, and nutrition coaching. Our packages range from $50-200/session with monthly memberships available. We specialize in strength training and mobility work for busy professionals."
                  className="min-h-[120px] resize-none"
                  defaultValue=""
                />
                <p className="text-xs text-muted-foreground">
                  Be specific about your offerings, pricing, and unique selling points
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Target Audience
                <span className="text-xs font-normal text-muted-foreground ml-2">
                  (Optional) • Enables personalized conversation flow
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="audience-description" className="text-sm font-medium">
                  Who are your ideal customers?
                </Label>
                <Textarea
                  id="audience-description"
                  placeholder="Describe your target audience demographics, pain points, goals, and communication preferences. Include details about their typical questions, concerns, and what they're looking for when they contact you.

Example: Busy professionals aged 25-45 who value efficiency and results. They often ask about scheduling flexibility, package deals, and results timelines. They prefer direct, no-nonsense communication and quick responses. Common concerns include time constraints and whether our approach fits their fitness level."
                  className="min-h-[120px] resize-none"
                  defaultValue=""
                />
                <p className="text-xs text-muted-foreground">
                  Help our AI understand who they're talking to and what matters to them
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageCircle className="h-5 w-5" />
                Communication Style & Voice
                <span className="text-xs font-normal text-muted-foreground ml-2">
                  (Optional) • AI learns to sound like you
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="communication-style" className="text-sm font-medium">
                  Share examples of how you communicate with customers
                </Label>
                <Textarea
                  id="communication-style"
                  placeholder="Paste examples of your actual messages, emails, or responses to customers. Include different scenarios like initial inquiries, follow-ups, scheduling, and problem resolution. This helps our AI match your tone, style, and personality.

Example messages:
- 'Hi Sarah! Thanks for reaching out about our training programs. I'd love to help you find the perfect fit for your goals...'
- 'Hey there! No worries about rescheduling - life happens! I have a few slots available this week...'
- 'That's a great question about our nutrition coaching. Here's what's included...'

The more examples you provide, the better our AI can sound like you!"
                  className="min-h-[160px] resize-none"
                  defaultValue=""
                />
                <p className="text-xs text-muted-foreground">
                  Include various scenarios: greetings, explanations, problem-solving, and closings
                </p>
              </div>
            </CardContent>
          </Card>

          <div className="flex gap-3">
            <Button size="lg" className="gap-2">
              <Save className="h-4 w-4" />
              Save Project Configuration
            </Button>
            <Button variant="outline" size="lg" onClick={() => router.push('/')}>
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

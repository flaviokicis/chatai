"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { getControllerUrl } from "@/lib/config";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft,
  Edit,
  Save,
  X,
  AlertTriangle,
  MessageSquare,
  FileJson,
  Shield,
} from "lucide-react";
import dynamic from "next/dynamic";

// Dynamically import Monaco Editor (most popular JSON editor in 2025)
const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-96 bg-gray-50 rounded-md">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-2 text-sm text-gray-600">Loading JSON Editor...</p>
      </div>
    </div>
  ),
});

interface Flow {
  id: string;
  name: string;
  flow_id: string;
  definition: any;
  created_at: string;
  updated_at: string;
}

interface Tenant {
  id: string;
  owner_first_name: string;
  owner_last_name: string;
  owner_email: string;
}

// Required for static export with dynamic routes
export async function generateStaticParams() {
  // Return empty array - these pages will be generated at request time
  return [];
}

export default function AdminFlowsPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params?.id as string;

  const [flows, setFlows] = useState<Flow[]>([]);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingFlow, setEditingFlow] = useState<Flow | null>(null);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [jsonContent, setJsonContent] = useState("");
  const [jsonError, setJsonError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (tenantId) {
      fetchFlows();
      fetchTenant();
    }
  }, [tenantId]);

  const fetchTenant = async () => {
    try {
      const response = await fetch("http://localhost:8080/controller/tenants", {
        credentials: "include",
      });

      if (response.status === 401) {
        router.push("/controller");
        return;
      }

      if (!response.ok) {
        throw new Error("Failed to fetch tenant");
      }

      const tenants = await response.json();
      const currentTenant = tenants.find((t: Tenant) => t.id === tenantId);
      if (currentTenant) {
        setTenant(currentTenant);
      }
    } catch (err) {
      setError("Failed to load tenant information.");
    }
  };

  const fetchFlows = async () => {
    try {
      const response = await fetch(`/api/admin/tenants/${tenantId}/flows`, {
        credentials: "include",
      });

      if (response.status === 401) {
        router.push("/controller");
        return;
      }

      if (!response.ok) {
        throw new Error("Failed to fetch flows");
      }

      const data = await response.json();
      setFlows(data);
    } catch (err) {
      setError("Failed to load flows. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleEditFlow = (flow: Flow) => {
    setEditingFlow(flow);
    setJsonContent(JSON.stringify(flow.definition, null, 2));
    setJsonError("");
    setShowEditDialog(true);
  };

  const handleSaveFlow = async () => {
    if (!editingFlow) return;

    // Validate JSON
    try {
      const parsedJson = JSON.parse(jsonContent);
      setJsonError("");
    } catch (err) {
      setJsonError("Invalid JSON format. Please fix the syntax errors.");
      return;
    }

    setSaving(true);

    try {
      const response = await fetch(`/api/admin/flows/${editingFlow.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          definition: JSON.parse(jsonContent),
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to update flow");
      }

      await fetchFlows();
      setShowEditDialog(false);
      setEditingFlow(null);
      setJsonContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update flow");
    } finally {
      setSaving(false);
    }
  };

  const handleJsonChange = (value: string | undefined) => {
    setJsonContent(value || "");
    setJsonError("");
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading flows...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <Button
              variant="outline"
              onClick={() => router.push("/controller/tenants")}
              className="mr-2"
            >
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back
            </Button>
            <div className="h-8 w-8 flex items-center justify-center rounded-full bg-blue-100">
              <Shield className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Flow Management</h1>
              {tenant && (
                <p className="text-sm text-gray-600">
                  {tenant.owner_first_name} {tenant.owner_last_name} • {tenant.owner_email}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Flows Table */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center">
                <MessageSquare className="h-5 w-5 mr-2" />
                Flows ({flows.length})
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Flow ID</TableHead>
                  <TableHead>Nodes</TableHead>
                  <TableHead>Last Updated</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flows.map((flow) => (
                  <TableRow key={flow.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{flow.name}</p>
                        <p className="text-sm text-gray-500">ID: {flow.id.slice(0, 8)}...</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{flow.flow_id}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {flow.definition?.nodes?.length || 0} nodes
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {new Date(flow.updated_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleEditFlow(flow)}
                        className="flex items-center"
                      >
                        <FileJson className="h-3 w-3 mr-1" />
                        Edit JSON
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {flows.length === 0 && (
              <div className="text-center py-8">
                <MessageSquare className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500">No flows found for this tenant.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Edit Flow Dialog with JSON Editor */}
        <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
          <DialogContent className="max-w-6xl h-[80vh] flex flex-col">
            <DialogHeader>
              <DialogTitle className="flex items-center">
                <FileJson className="h-5 w-5 mr-2" />
                Edit Flow JSON: {editingFlow?.name}
              </DialogTitle>
            </DialogHeader>

            <div className="flex-1 flex flex-col space-y-4">
              {/* Flow Info */}
              {editingFlow && (
                <div className="bg-gray-50 p-3 rounded-md text-sm">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="font-medium">Flow ID:</span> {editingFlow.flow_id}
                    </div>
                    <div>
                      <span className="font-medium">Nodes:</span>{" "}
                      {editingFlow.definition?.nodes?.length || 0}
                    </div>
                  </div>
                </div>
              )}

              {/* JSON Error */}
              {jsonError && (
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>{jsonError}</AlertDescription>
                </Alert>
              )}

              {/* Monaco JSON Editor */}
              <div className="flex-1 border rounded-md overflow-hidden">
                <MonacoEditor
                  height="100%"
                  defaultLanguage="json"
                  value={jsonContent}
                  onChange={handleJsonChange}
                  options={{
                    minimap: { enabled: true },
                    formatOnPaste: true,
                    formatOnType: true,
                    automaticLayout: true,
                    scrollBeyondLastLine: false,
                    wordWrap: "on",
                    lineNumbers: "on",
                    folding: true,
                    bracketPairColorization: { enabled: true },
                    renderWhitespace: "selection",
                    tabSize: 2,
                    insertSpaces: true,
                  }}
                  theme="vs-light"
                />
              </div>

              {/* Actions */}
              <div className="flex justify-between">
                <div className="text-sm text-gray-500">
                  💡 Tip: Use Ctrl+Shift+F to format JSON automatically
                </div>
                <div className="flex space-x-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowEditDialog(false);
                      setEditingFlow(null);
                      setJsonContent("");
                      setJsonError("");
                    }}
                  >
                    <X className="h-4 w-4 mr-1" />
                    Cancel
                  </Button>
                  <Button onClick={handleSaveFlow} disabled={saving || !!jsonError}>
                    {saving ? (
                      <div className="flex items-center">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                        Saving...
                      </div>
                    ) : (
                      <>
                        <Save className="h-4 w-4 mr-1" />
                        Save Flow
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}

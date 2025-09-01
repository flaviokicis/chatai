"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
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
  Save,
  X,
  AlertTriangle,
  MessageSquare,
  FileJson,
  Shield,
} from "lucide-react";
import { getControllerUrl } from "@/lib/config";

// Dynamically import Monaco Editor for optimal loading
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

// Type definitions
interface FlowDefinition {
  schema_version: string;
  id: string;
  entry: string;
  metadata?: {
    name?: string;
    description?: string;
    version?: string;
  };
  nodes?: Array<{
    id: string;
    kind: string;
    [key: string]: unknown;
  }>;
  [key: string]: unknown;
}

interface Flow {
  id: string;
  name: string;
  flow_id: string;
  definition: FlowDefinition;
  created_at: string;
  updated_at: string;
}

interface Tenant {
  id: string;
  owner_first_name: string;
  owner_last_name: string;
  owner_email: string;
}

interface ApiError {
  detail?: string;
  message?: string;
}

interface FlowManagementClientProps {
  tenantId: string;
}

export default function FlowManagementClient({ tenantId }: FlowManagementClientProps): React.JSX.Element {
  const router = useRouter();

  // State management
  const [flows, setFlows] = useState<Flow[]>([]);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingFlow, setEditingFlow] = useState<Flow | null>(null);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [jsonContent, setJsonContent] = useState("");
  const [jsonError, setJsonError] = useState("");
  const [saving, setSaving] = useState(false);

  // API functions with proper error handling
  const fetchTenant = useCallback(async (): Promise<void> => {
    try {
      const response = await fetch(getControllerUrl("/tenants"), {
        credentials: "include",
      });

      if (response.status === 401) {
        router.push("/controller");
        return;
      }

      if (!response.ok) {
        throw new Error(`Failed to fetch tenant: ${response.status}`);
      }

      const tenants: Tenant[] = await response.json();
      const currentTenant = tenants.find((t) => t.id === tenantId);
      if (currentTenant) {
        setTenant(currentTenant);
      } else {
        setError("Tenant not found");
      }
    } catch (err) {
      console.error("Error loading tenant:", err);
      setError("Failed to load tenant information.");
    }
  }, [tenantId, router]);

  const fetchFlows = useCallback(async (): Promise<void> => {
    try {
      const response = await fetch(getControllerUrl(`/tenants/${tenantId}/flows`), {
        credentials: "include",
      });

      if (response.status === 401) {
        router.push("/controller");
        return;
      }

      if (!response.ok) {
        throw new Error(`Failed to fetch flows: ${response.status}`);
      }

      const data: Flow[] = await response.json();
      setFlows(data);
    } catch (err) {
      console.error("Error loading flows:", err);
      setError("Failed to load flows. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [tenantId, router]);

  // Effects
  useEffect(() => {
    fetchFlows();
    fetchTenant();
  }, [fetchFlows, fetchTenant]);

  // Event handlers
  const handleEditFlow = (flow: Flow): void => {
    setEditingFlow(flow);
    setJsonContent(JSON.stringify(flow.definition, null, 2));
    setJsonError("");
    setShowEditDialog(true);
  };

  const handleSaveFlow = async (): Promise<void> => {
    if (!editingFlow) return;

    // Validate JSON with comprehensive error handling
    let parsedDefinition: FlowDefinition;
    try {
      parsedDefinition = JSON.parse(jsonContent) as FlowDefinition;
      setJsonError("");
      
      // Validate required flow structure
      if (!parsedDefinition.schema_version || !parsedDefinition.id || !parsedDefinition.entry) {
        setJsonError("Flow must have schema_version, id, and entry fields.");
        return;
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Invalid JSON format";
      setJsonError(`JSON Syntax Error: ${errorMessage}`);
      return;
    }

    setSaving(true);

    try {
      const response = await fetch(getControllerUrl(`/flows/${editingFlow.id}`), {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          definition: parsedDefinition,
        }),
      });

      if (!response.ok) {
        const errorData: ApiError = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(errorData.detail || errorData.message || "Failed to update flow");
      }

      await fetchFlows();
      setShowEditDialog(false);
      setEditingFlow(null);
      setJsonContent("");
      setError("");
    } catch (err) {
      console.error("Error updating flow:", err);
      setError(err instanceof Error ? err.message : "Failed to update flow");
    } finally {
      setSaving(false);
    }
  };

  const handleJsonChange = (value: string | undefined): void => {
    setJsonContent(value || "");
    setJsonError("");
  };

  const handleCloseDialog = (): void => {
    setShowEditDialog(false);
    setEditingFlow(null);
    setJsonContent("");
    setJsonError("");
  };

  // Loading state
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

        {/* Flow JSON Editor Dialog */}
        <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
          <DialogContent className="max-w-6xl h-[80vh] flex flex-col">
            <DialogHeader>
              <DialogTitle className="flex items-center">
                <FileJson className="h-5 w-5 mr-2" />
                Edit Flow JSON: {editingFlow?.name}
              </DialogTitle>
            </DialogHeader>

            <div className="flex-1 flex flex-col space-y-4">
              {/* Flow Information */}
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

              {/* JSON Validation Error */}
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

              {/* Action Bar */}
              <div className="flex justify-between items-center">
                <div className="text-sm text-gray-500">
                  💡 Tip: Use Ctrl+Shift+F to format JSON automatically
                </div>
                <div className="flex space-x-2">
                  <Button
                    variant="outline"
                    onClick={handleCloseDialog}
                  >
                    <X className="h-4 w-4 mr-1" />
                    Cancel
                  </Button>
                  <Button 
                    onClick={handleSaveFlow} 
                    disabled={saving || !!jsonError}
                  >
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
"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { getControllerUrl } from "@/lib/config";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
  Users,
  Plus,
  Edit,
  Trash2,
  Phone,
  MessageSquare,
  LogOut,
  Shield,
  AlertTriangle,
  Settings,
  CheckSquare,
  Square,
} from "lucide-react";

interface Tenant {
  id: string;
  owner_first_name: string;
  owner_last_name: string;
  owner_email: string;
  created_at: string;
  updated_at: string;
  project_description?: string;
  target_audience?: string;
  communication_style?: string;
  channel_count: number;
  flow_count: number;
}

interface TenantFormData {
  owner_first_name: string;
  owner_last_name: string;
  owner_email: string;
  project_description?: string;
  target_audience?: string;
  communication_style?: string;
}

export default function TenantsManagementPage(): React.JSX.Element {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null);
  const [formData, setFormData] = useState<TenantFormData>({
    owner_first_name: "",
    owner_last_name: "",
    owner_email: "",
    project_description: "",
    target_audience: "",
    communication_style: "",
  });
  const [formLoading, setFormLoading] = useState(false);
  const [selectedTenants, setSelectedTenants] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const router = useRouter();

  const fetchTenants = useCallback(async (): Promise<void> => {
    try {
      const response = await fetch(getControllerUrl("/tenants"), {
        credentials: "include",
      });

      if (response.status === 401) {
        router.push("/controller");
        return;
      }

      if (!response.ok) {
        throw new Error("Failed to fetch tenants");
      }

      const data = await response.json();
      setTenants(data);
    } catch (err) {
      console.error("Error loading tenants:", err);
      if (err instanceof Error && err.message.includes("Unexpected token")) {
        setError("Server returned invalid response. Please check if the backend is running.");
      } else {
        setError("Failed to load tenants. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  const handleLogout = async (): Promise<void> => {
    try {
      await fetch(getControllerUrl("/logout"), {
        method: "POST",
        credentials: "include",
      });
      router.push("/controller");
    } catch {
      // Force redirect even if logout fails
      router.push("/controller");
    }
  };

  const resetForm = (): void => {
    setFormData({
      owner_first_name: "",
      owner_last_name: "",
      owner_email: "",
      project_description: "",
      target_audience: "",
      communication_style: "",
    });
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormLoading(true);

    try {
      const response = await fetch(getControllerUrl("/tenants"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to create tenant");
      }

      await fetchTenants();
      setShowCreateDialog(false);
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create tenant");
    } finally {
      setFormLoading(false);
    }
  };

  const handleEdit = (tenant: Tenant) => {
    setEditingTenant(tenant);
    setFormData({
      owner_first_name: tenant.owner_first_name,
      owner_last_name: tenant.owner_last_name,
      owner_email: tenant.owner_email,
      project_description: tenant.project_description || "",
      target_audience: tenant.target_audience || "",
      communication_style: tenant.communication_style || "",
    });
    setShowEditDialog(true);
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTenant) return;

    setFormLoading(true);

    try {
      const response = await fetch(getControllerUrl(`/tenants/${editingTenant.id}`), {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to update tenant");
      }

      await fetchTenants();
      setShowEditDialog(false);
      setEditingTenant(null);
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update tenant");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (tenant: Tenant) => {
    if (!confirm(`Are you sure you want to delete tenant "${tenant.owner_first_name} ${tenant.owner_last_name}"? This will delete ALL associated data including channels, flows, contacts, and messages. This action cannot be undone.`)) {
      return;
    }

    try {
      const response = await fetch(getControllerUrl(`/tenants/${tenant.id}`), {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to delete tenant");
      }

      await fetchTenants();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete tenant");
    }
  };

  const handleSelectTenant = (tenantId: string) => {
    const newSelected = new Set(selectedTenants);
    if (newSelected.has(tenantId)) {
      newSelected.delete(tenantId);
    } else {
      newSelected.add(tenantId);
    }
    setSelectedTenants(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedTenants.size === tenants.length) {
      setSelectedTenants(new Set());
    } else {
      setSelectedTenants(new Set(tenants.map(t => t.id)));
    }
  };

  const handleDeleteTestUsers = async () => {
    const testTenants = tenants.filter(tenant => 
      tenant.owner_first_name === "Test User" && 
      tenant.owner_email.includes("test-") && 
      tenant.owner_email.includes("@example.com")
    );
    
    if (testTenants.length === 0) {
      setError("No test users found to delete.");
      return;
    }

    // Keep the first test user, delete the rest
    const tenantsToDelete = testTenants.slice(1);
    
    if (!confirm(`Are you sure you want to delete ${tenantsToDelete.length} test users? This will delete ALL associated data including channels, flows, contacts, and messages. This action cannot be undone.\n\nThe first test user will be kept.`)) {
      return;
    }

    setBulkDeleting(true);
    let deletedCount = 0;
    let failedCount = 0;

    for (const tenant of tenantsToDelete) {
      try {
        const response = await fetch(getControllerUrl(`/tenants/${tenant.id}`), {
          method: "DELETE",
          credentials: "include",
        });

        if (!response.ok) {
          const error = await response.json();
          console.error(`Failed to delete tenant ${tenant.id}:`, error.detail);
          failedCount++;
        } else {
          deletedCount++;
        }
      } catch (err) {
        console.error(`Error deleting tenant ${tenant.id}:`, err);
        failedCount++;
      }
    }

    setBulkDeleting(false);
    
    if (failedCount > 0) {
      setError(`Deleted ${deletedCount} test users, but ${failedCount} failed to delete. Check console for details.`);
    }
    
    await fetchTenants();
  };

  const handleBulkDelete = async () => {
    if (selectedTenants.size === 0) {
      setError("No tenants selected for deletion.");
      return;
    }

    const selectedTenantsList = tenants.filter(t => selectedTenants.has(t.id));
    
    if (!confirm(`Are you sure you want to delete ${selectedTenants.size} selected tenants? This will delete ALL associated data including channels, flows, contacts, and messages. This action cannot be undone.`)) {
      return;
    }

    setBulkDeleting(true);
    let deletedCount = 0;
    let failedCount = 0;

    for (const tenant of selectedTenantsList) {
      try {
        const response = await fetch(getControllerUrl(`/tenants/${tenant.id}`), {
          method: "DELETE",
          credentials: "include",
        });

        if (!response.ok) {
          const error = await response.json();
          console.error(`Failed to delete tenant ${tenant.id}:`, error.detail);
          failedCount++;
        } else {
          deletedCount++;
        }
      } catch (err) {
        console.error(`Error deleting tenant ${tenant.id}:`, err);
        failedCount++;
      }
    }

    setBulkDeleting(false);
    setSelectedTenants(new Set());
    
    if (failedCount > 0) {
      setError(`Deleted ${deletedCount} tenants, but ${failedCount} failed to delete. Check console for details.`);
    }
    
    await fetchTenants();
  };

  const navigateToFlows = (tenantId: string) => {
    router.push(`/controller/tenants/${tenantId}/flows`);
  };

  const navigateToConversations = () => {
    router.push("/controller/conversations");
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading tenants...</p>
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
            <div className="h-8 w-8 flex items-center justify-center rounded-full bg-blue-100">
              <Shield className="h-4 w-4 text-blue-600" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
          </div>
          <div className="flex space-x-2">
            <Button onClick={navigateToConversations} variant="outline">
              <MessageSquare className="h-4 w-4 mr-2" />
              Conversations
            </Button>
            <Button onClick={handleLogout} variant="outline">
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <Users className="h-8 w-8 text-blue-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">Total Tenants</p>
                  <p className="text-2xl font-bold text-gray-900">{tenants.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <Phone className="h-8 w-8 text-green-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">Total Channels</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {tenants.reduce((sum, t) => sum + t.channel_count, 0)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <MessageSquare className="h-8 w-8 text-purple-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">Total Flows</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {tenants.reduce((sum, t) => sum + t.flow_count, 0)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Tenants Table */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Tenant Management</CardTitle>
              <div className="flex space-x-2">
                {selectedTenants.size > 0 && (
                  <Button
                    variant="outline"
                    onClick={handleBulkDelete}
                    disabled={bulkDeleting}
                    className="text-red-600 hover:text-red-700"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete Selected ({selectedTenants.size})
                  </Button>
                )}
                <Button
                  variant="outline"
                  onClick={handleDeleteTestUsers}
                  disabled={bulkDeleting}
                  className="text-orange-600 hover:text-orange-700"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {bulkDeleting ? "Deleting..." : "Delete Test Users"}
                </Button>
                <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
                  <DialogTrigger asChild>
                    <Button>
                      <Plus className="h-4 w-4 mr-2" />
                      Create Tenant
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-2xl">
                    <DialogHeader>
                      <DialogTitle>Create New Tenant</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={handleCreate} className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label htmlFor="firstName">First Name</Label>
                          <Input
                            id="firstName"
                            value={formData.owner_first_name}
                            onChange={(e) =>
                              setFormData({ ...formData, owner_first_name: e.target.value })
                            }
                            required
                          />
                        </div>
                        <div>
                          <Label htmlFor="lastName">Last Name</Label>
                          <Input
                            id="lastName"
                            value={formData.owner_last_name}
                            onChange={(e) =>
                              setFormData({ ...formData, owner_last_name: e.target.value })
                            }
                            required
                          />
                        </div>
                      </div>
                      <div>
                        <Label htmlFor="email">Email</Label>
                        <Input
                          id="email"
                          type="email"
                          value={formData.owner_email}
                          onChange={(e) =>
                            setFormData({ ...formData, owner_email: e.target.value })
                          }
                          required
                        />
                      </div>
                      <div>
                        <Label htmlFor="description">Project Description</Label>
                        <Textarea
                          id="description"
                          value={formData.project_description}
                          onChange={(e) =>
                            setFormData({ ...formData, project_description: e.target.value })
                          }
                          placeholder="Describe the business or project..."
                        />
                      </div>
                      <div>
                        <Label htmlFor="audience">Target Audience</Label>
                        <Textarea
                          id="audience"
                          value={formData.target_audience}
                          onChange={(e) =>
                            setFormData({ ...formData, target_audience: e.target.value })
                          }
                          placeholder="Who is the target audience?"
                        />
                      </div>
                      <div>
                        <Label htmlFor="style">Communication Style</Label>
                        <Textarea
                          id="style"
                          value={formData.communication_style}
                          onChange={(e) =>
                            setFormData({ ...formData, communication_style: e.target.value })
                          }
                          placeholder="Describe the desired communication tone and style..."
                        />
                      </div>
                      <div className="flex justify-end space-x-2">
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => {
                            setShowCreateDialog(false);
                            resetForm();
                          }}
                        >
                          Cancel
                        </Button>
                        <Button type="submit" disabled={formLoading}>
                          {formLoading ? "Creating..." : "Create Tenant"}
                        </Button>
                      </div>
                    </form>
                  </DialogContent>
                </Dialog>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <button
                      onClick={handleSelectAll}
                      className="flex items-center justify-center w-5 h-5"
                    >
                      {selectedTenants.size === tenants.length && tenants.length > 0 ? (
                        <CheckSquare className="h-4 w-4" />
                      ) : (
                        <Square className="h-4 w-4" />
                      )}
                    </button>
                  </TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Channels</TableHead>
                  <TableHead>Flows</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tenants.map((tenant) => (
                  <TableRow key={tenant.id}>
                    <TableCell>
                      <button
                        onClick={() => handleSelectTenant(tenant.id)}
                        className="flex items-center justify-center w-5 h-5"
                      >
                        {selectedTenants.has(tenant.id) ? (
                          <CheckSquare className="h-4 w-4" />
                        ) : (
                          <Square className="h-4 w-4" />
                        )}
                      </button>
                    </TableCell>
                    <TableCell>
                      <div>
                        <p className="font-medium">
                          {tenant.owner_first_name} {tenant.owner_last_name}
                        </p>
                        <p className="text-sm text-gray-500">ID: {tenant.id.slice(0, 8)}...</p>
                      </div>
                    </TableCell>
                    <TableCell>{tenant.owner_email}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{tenant.channel_count}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{tenant.flow_count}</Badge>
                    </TableCell>
                    <TableCell>
                      {new Date(tenant.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <div className="flex space-x-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => navigateToFlows(tenant.id)}
                        >
                          <MessageSquare className="h-3 w-3 mr-1" />
                          Flows
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleEdit(tenant)}
                        >
                          <Edit className="h-3 w-3" />
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDelete(tenant)}
                          className="text-red-600 hover:text-red-700"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {tenants.length === 0 && (
              <div className="text-center py-8">
                <p className="text-gray-500">No tenants found. Create your first tenant to get started.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Edit Dialog */}
        <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Edit Tenant</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleUpdate} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="editFirstName">First Name</Label>
                  <Input
                    id="editFirstName"
                    value={formData.owner_first_name}
                    onChange={(e) =>
                      setFormData({ ...formData, owner_first_name: e.target.value })
                    }
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="editLastName">Last Name</Label>
                  <Input
                    id="editLastName"
                    value={formData.owner_last_name}
                    onChange={(e) =>
                      setFormData({ ...formData, owner_last_name: e.target.value })
                    }
                    required
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="editEmail">Email</Label>
                <Input
                  id="editEmail"
                  type="email"
                  value={formData.owner_email}
                  onChange={(e) =>
                    setFormData({ ...formData, owner_email: e.target.value })
                  }
                  required
                />
              </div>
              <div>
                <Label htmlFor="editDescription">Project Description</Label>
                <Textarea
                  id="editDescription"
                  value={formData.project_description}
                  onChange={(e) =>
                    setFormData({ ...formData, project_description: e.target.value })
                  }
                  placeholder="Describe the business or project..."
                />
              </div>
              <div>
                <Label htmlFor="editAudience">Target Audience</Label>
                <Textarea
                  id="editAudience"
                  value={formData.target_audience}
                  onChange={(e) =>
                    setFormData({ ...formData, target_audience: e.target.value })
                  }
                  placeholder="Who is the target audience?"
                />
              </div>
              <div>
                <Label htmlFor="editStyle">Communication Style</Label>
                <Textarea
                  id="editStyle"
                  value={formData.communication_style}
                  onChange={(e) =>
                    setFormData({ ...formData, communication_style: e.target.value })
                  }
                  placeholder="Describe the desired communication tone and style..."
                />
              </div>
              <div className="flex justify-end space-x-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowEditDialog(false);
                    setEditingTenant(null);
                    resetForm();
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={formLoading}>
                  {formLoading ? "Updating..." : "Update Tenant"}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}

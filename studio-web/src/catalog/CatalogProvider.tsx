// Fetches the framework's live shape once at boot and exposes it via context.
// Everything downstream binds to this — no catalog value or layer field is ever
// hardcoded, so pointing at a newer framework version just works.

import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Catalogs, NodeTypes } from "../api/types";

interface CatalogContextValue {
  catalogs: Catalogs | undefined;
  nodeTypes: NodeTypes | undefined;
  connected: boolean;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

const CatalogContext = createContext<CatalogContextValue | null>(null);

export function CatalogProvider({ children }: { children: ReactNode }) {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 5000,
    retry: false,
  });
  const catalogs = useQuery({ queryKey: ["catalogs"], queryFn: api.catalogs, retry: false });
  const nodeTypes = useQuery({ queryKey: ["nodeTypes"], queryFn: api.nodeTypes, retry: false });

  const connected = health.isSuccess && catalogs.isSuccess && nodeTypes.isSuccess;
  const loading = health.isLoading || catalogs.isLoading || nodeTypes.isLoading;
  const error =
    (health.error || catalogs.error || nodeTypes.error)?.message ?? null;

  const value: CatalogContextValue = {
    catalogs: catalogs.data,
    nodeTypes: nodeTypes.data,
    connected,
    loading,
    error,
    refetch: () => {
      health.refetch();
      catalogs.refetch();
      nodeTypes.refetch();
    },
  };

  return <CatalogContext.Provider value={value}>{children}</CatalogContext.Provider>;
}

export function useCatalog(): CatalogContextValue {
  const ctx = useContext(CatalogContext);
  if (!ctx) throw new Error("useCatalog must be used within CatalogProvider");
  return ctx;
}

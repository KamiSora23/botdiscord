"use client";

import { useCallback } from "react";

import { api } from "@/lib/api";

export function useLogout() {
  return useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      window.location.href = "/";
    }
  }, []);
}

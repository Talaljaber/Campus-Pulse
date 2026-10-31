"use client";

import { useServiceHealth } from "@/hooks/useServiceHealth";
import { ServiceBanner } from "../ui/ServiceBanner";

/** Mounts the "AI waking up" banner once for the whole app (root layout). */
export function ServiceStatus() {
  return <ServiceBanner state={useServiceHealth()} />;
}

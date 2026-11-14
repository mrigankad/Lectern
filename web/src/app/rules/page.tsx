"use client";

import { Shield } from "lucide-react";
import { RulesPanel } from "@/components/RulesPanel";
import { AppShell } from "@/components/Shell";
import { PageHeader } from "@/components/ui";

export default function RulesPage() {
  return (
    <AppShell crumbs={[{ label: "Settings" }, { label: "Rules" }]}>
      <PageHeader icon={<Shield size={22} />} title="Rules" subtitle="Standing instructions for every agent, on every deck." />
      <RulesPanel className="max-w-[640px]" />
    </AppShell>
  );
}

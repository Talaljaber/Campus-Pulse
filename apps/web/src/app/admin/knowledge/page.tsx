import { KnowledgeScreen } from "@/components/admin/KnowledgeScreen";
import { requireProfile } from "@/lib/auth/guard";
import { nameOf } from "@/lib/auth/profile";

/** `/admin/knowledge`: upload and manage the documents the assistant can quote (P10.19). Admin only. */
export default async function AdminKnowledgePage() {
  const profile = await requireProfile(["admin"]);
  return <KnowledgeScreen alias={profile.alias} name={nameOf(profile)} />;
}

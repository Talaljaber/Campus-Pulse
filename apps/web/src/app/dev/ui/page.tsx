import { notFound } from "next/navigation";
import { KitchenSink } from "./KitchenSink";

/** Dev-only kitchen sink (ARCHITECTURE 1.7). Returns 404 in production builds. */
export default function DevUiPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <KitchenSink />;
}

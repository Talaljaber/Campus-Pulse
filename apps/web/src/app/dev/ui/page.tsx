import { notFound } from "next/navigation";

export default function DevUiPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return (
    <main>
      <h1>UI kitchen sink</h1>
    </main>
  );
}

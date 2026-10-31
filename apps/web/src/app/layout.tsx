import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CampusPulse",
  description: "Bilingual campus-request triage",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" dir="ltr">
      <body>{children}</body>
    </html>
  );
}

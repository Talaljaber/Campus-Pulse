import type { Metadata } from "next";
import { IBM_Plex_Sans_Arabic, Inter } from "next/font/google";
import { cookies, headers } from "next/headers";
import { ServiceStatus } from "@/components/shell/ServiceStatus";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { ToastProvider } from "@/components/ui/Toast";
import { LANG_COOKIE, dirOf, resolveLang } from "@/i18n";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });
const plexArabic = IBM_Plex_Sans_Arabic({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-plex-arabic",
});

export const metadata: Metadata = {
  title: "CampusPulse",
  description: "Bilingual campus-request triage for students. A prototype, not an official university service.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [jar, hdrs] = await Promise.all([cookies(), headers()]);
  const lang = resolveLang(jar.get(LANG_COOKIE)?.value, hdrs.get("accept-language"));
  return (
    <html lang={lang} dir={dirOf(lang)} className={`${inter.variable} ${plexArabic.variable}`}>
      <body>
        <RtlProvider lang={lang}>
          <ToastProvider>
            <div className="flex min-h-dvh flex-col">
              <ServiceStatus />
              <div className="flex flex-1 flex-col">{children}</div>
              <SiteFooter />
            </div>
          </ToastProvider>
        </RtlProvider>
      </body>
    </html>
  );
}
